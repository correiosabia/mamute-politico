"""Quota accounting for chatbot usage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
import json
import logging
from typing import Any, Mapping, Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..schemas import ChatQuotaResponse

logger = logging.getLogger(__name__)

COUNTED_USAGE_STATUSES = ("started", "completed", "failed", "cancelled")


class ChatQuotaConfigError(RuntimeError):
    """Raised when quota configuration is invalid."""


@dataclass(frozen=True)
class ChatProject:
    id: int
    email: str
    product_id: Optional[str]
    tier_slug: str
    tier_details: Mapping[str, Any]


@dataclass(frozen=True)
class ChatUsageStart:
    usage_id: Optional[int]
    quota: ChatQuotaResponse


def current_period_start(now: Optional[datetime] = None) -> date:
    """Return the first day of the current São Paulo calendar month."""

    tz = ZoneInfo("America/Sao_Paulo")
    local_now = now.astimezone(tz) if now is not None else datetime.now(tz)
    return local_now.date().replace(day=1)


def next_period_start(period_start: date) -> datetime:
    """Return the next quota reset datetime in São Paulo time."""

    year = period_start.year + (1 if period_start.month == 12 else 0)
    month = 1 if period_start.month == 12 else period_start.month + 1
    return datetime.combine(
        date(year, month, 1),
        time.min,
        tzinfo=ZoneInfo("America/Sao_Paulo"),
    )


def disabled_quota_response() -> ChatQuotaResponse:
    period_start = current_period_start()
    return ChatQuotaResponse(
        enabled=False,
        limit=None,
        used=0,
        remaining=None,
        reset_at=next_period_start(period_start),
        limit_reached=False,
    )


def _coerce_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, Mapping):
            return parsed
    return {}


def _parse_monthly_limits(raw: str) -> dict[str, int]:
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ChatQuotaConfigError(
            "MAMUTE_CHATBOT_MONTHLY_LIMITS_JSON não é um JSON válido."
        ) from exc
    if not isinstance(payload, Mapping):
        raise ChatQuotaConfigError(
            "MAMUTE_CHATBOT_MONTHLY_LIMITS_JSON deve ser um objeto por slug."
        )

    limits: dict[str, int] = {}
    for key, value in payload.items():
        slug = str(key).strip()
        if not slug:
            continue
        try:
            limit = int(value)
        except (TypeError, ValueError) as exc:
            raise ChatQuotaConfigError(
                f"Limite de chatbot inválido para o slug {slug!r}."
            ) from exc
        limits[slug] = max(0, limit)
    return limits


def _parse_tier_entitlement_limits(raw: str) -> Mapping[str, Any]:
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ChatQuotaConfigError("MAMUTE_TIER_LIMITS_JSON não é um JSON válido.") from exc
    if not isinstance(payload, Mapping):
        raise ChatQuotaConfigError("MAMUTE_TIER_LIMITS_JSON deve ser um objeto por slug.")
    return payload


def _limit_from_tier_entitlements(
    project: ChatProject,
    tier_limits: Mapping[str, Any],
) -> int | None:
    for key in (project.tier_slug, project.product_id):
        if not key or key not in tier_limits:
            continue
        entry = tier_limits[key]
        if not isinstance(entry, Mapping):
            continue
        for detail_key in ("qtd_consultas_ia_mes", "ai_queries_monthly_limit"):
            if detail_key not in entry:
                continue
            try:
                return max(0, int(entry[detail_key]))
            except (TypeError, ValueError) as exc:
                raise ChatQuotaConfigError(
                    f"Limite {detail_key!r} inválido para o tier {key!r}."
                ) from exc
    return None


def _tier_slug(product_id: Optional[str], detalhes: Mapping[str, Any]) -> str:
    ghost = _coerce_mapping(detalhes.get("ghost"))
    slug = ghost.get("slug")
    if isinstance(slug, str) and slug.strip():
        return slug.strip()
    if product_id == "free":
        return "free"
    return (product_id or "free").strip() or "free"


def resolve_monthly_limit(project: ChatProject) -> int:
    """Resolve the monthly chatbot quota for a project."""

    settings = get_settings()
    env_limits = _parse_monthly_limits(settings.chatbot_monthly_limits_json)
    for key in (project.tier_slug, project.product_id):
        if key and key in env_limits:
            return env_limits[key]

    tier_env_limit = _limit_from_tier_entitlements(
        project,
        _parse_tier_entitlement_limits(settings.tier_limits_json),
    )
    if tier_env_limit is not None:
        return tier_env_limit

    for detail_key in ("qtd_consultas_ia_mes", "ai_queries_monthly_limit"):
        raw_limit = project.tier_details.get(detail_key)
        if raw_limit is None:
            continue
        try:
            return max(0, int(raw_limit))
        except (TypeError, ValueError) as exc:
            raise ChatQuotaConfigError(
                f"Valor inválido de {detail_key} para o tier {project.tier_slug!r}."
            ) from exc

    return max(0, int(settings.chatbot_default_monthly_limit))


def _load_project(
    session: Session,
    email: str,
    *,
    lock_for_update: bool = False,
) -> ChatProject:
    stmt = """
        SELECT
            p.id AS project_id,
            p.email AS project_email,
            COALESCE(t.product_id, p.cliente) AS product_id,
            t.detalhes AS tier_details
        FROM projetos p
        LEFT JOIN tiers t ON t.id = p.tier_id
        WHERE p.email = :email
          AND p.deleted_at IS NULL
        LIMIT 1
    """
    dialect_name = getattr(session.get_bind().dialect, "name", "")
    if lock_for_update and dialect_name == "postgresql":
        stmt += " FOR UPDATE OF p"

    row = session.execute(text(stmt), {"email": email}).mappings().first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projeto não encontrado para o e-mail autenticado.",
        )

    tier_details = _coerce_mapping(row.get("tier_details"))
    product_id = row.get("product_id")
    product_id = str(product_id).strip() if product_id is not None else None
    return ChatProject(
        id=int(row["project_id"]),
        email=str(row["project_email"]),
        product_id=product_id,
        tier_slug=_tier_slug(product_id, tier_details),
        tier_details=tier_details,
    )


def _usage_count(session: Session, project_id: int, period_start: date) -> int:
    stmt = text(
        """
        SELECT COUNT(*)
        FROM chatbot_usage
        WHERE projeto_id = :project_id
          AND period_start = :period_start
          AND status IN :statuses
        """
    ).bindparams(bindparam("statuses", expanding=True))
    return int(
        session.execute(
            stmt,
            {
                "project_id": project_id,
                "period_start": period_start,
                "statuses": list(COUNTED_USAGE_STATUSES),
            },
        ).scalar_one()
        or 0
    )


def get_chat_quota(session: Session, email: str) -> ChatQuotaResponse:
    """Return quota status for an authenticated project."""

    settings = get_settings()
    period_start = current_period_start()
    reset_at = next_period_start(period_start)
    if not settings.chatbot_quota_enabled:
        return disabled_quota_response()

    project = _load_project(session, email)
    limit = resolve_monthly_limit(project)
    used = _usage_count(session, project.id, period_start)
    remaining = max(0, limit - used)
    return ChatQuotaResponse(
        enabled=True,
        limit=limit,
        used=used,
        remaining=remaining,
        reset_at=reset_at,
        limit_reached=used >= limit,
    )


def start_chat_usage(
    session: Session,
    email: str,
    *,
    request_id: str,
    question_chars: int,
    model: str,
) -> ChatUsageStart:
    """Reserve one chatbot usage unit before the LLM call starts."""

    settings = get_settings()
    period_start = current_period_start()
    reset_at = next_period_start(period_start)
    if not settings.chatbot_quota_enabled:
        return ChatUsageStart(
            usage_id=None,
            quota=disabled_quota_response(),
        )

    project = _load_project(session, email, lock_for_update=True)
    limit = resolve_monthly_limit(project)
    used = _usage_count(session, project.id, period_start)
    if used >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Limite mensal de consultas IA atingido para seu plano "
                f"({used}/{limit})."
            ),
        )

    row = session.execute(
        text(
            """
            INSERT INTO chatbot_usage
                (
                    projeto_id,
                    email,
                    request_id,
                    period_start,
                    status,
                    question_chars,
                    answer_chars,
                    model
                )
            VALUES
                (
                    :project_id,
                    :email,
                    :request_id,
                    :period_start,
                    'started',
                    :question_chars,
                    0,
                    :model
                )
            RETURNING id
            """
        ),
        {
            "project_id": project.id,
            "email": project.email,
            "request_id": request_id,
            "period_start": period_start,
            "question_chars": max(0, question_chars),
            "model": model,
        },
    ).first()
    session.commit()

    next_used = used + 1
    remaining = max(0, limit - next_used)
    return ChatUsageStart(
        usage_id=int(row[0]) if row else None,
        quota=ChatQuotaResponse(
            enabled=True,
            limit=limit,
            used=next_used,
            remaining=remaining,
            reset_at=reset_at,
            limit_reached=next_used >= limit,
        ),
    )


def mark_chat_usage(
    session: Session,
    usage_id: Optional[int],
    *,
    status_value: str,
    answer_chars: int = 0,
) -> None:
    """Update the status of a previously reserved usage row."""

    if usage_id is None:
        return
    session.execute(
        text(
            """
            UPDATE chatbot_usage
            SET status = :status,
                answer_chars = :answer_chars,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :usage_id
            """
        ),
        {
            "usage_id": usage_id,
            "status": status_value,
            "answer_chars": max(0, answer_chars),
        },
    )
    session.commit()


__all__ = [
    "ChatQuotaConfigError",
    "ChatUsageStart",
    "current_period_start",
    "disabled_quota_response",
    "get_chat_quota",
    "mark_chat_usage",
    "resolve_monthly_limit",
    "start_chat_usage",
]
