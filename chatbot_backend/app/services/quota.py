"""Quota accounting for chatbot usage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import json
import logging
from typing import Any, Mapping, Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..schemas import ChatQuotaResponse, ChatQuotaWindow

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


def current_week_start(now: Optional[datetime] = None) -> date:
    """Return the Monday of the current São Paulo calendar week."""

    tz = ZoneInfo("America/Sao_Paulo")
    local_now = now.astimezone(tz) if now is not None else datetime.now(tz)
    today = local_now.date()
    return today - timedelta(days=today.weekday())


def next_week_start(week_start: date) -> datetime:
    """Return the next weekly quota reset datetime (next Monday) in SP time."""

    return datetime.combine(
        week_start + timedelta(days=7),
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
    """Resolve the monthly chatbot quota for a project (env > DB > default)."""

    settings = get_settings()

    # 1) Env: override por slug do chatbot.
    env_limits = _parse_monthly_limits(settings.chatbot_monthly_limits_json)
    for key in (project.tier_slug, project.product_id):
        if key and key in env_limits:
            return env_limits[key]

    # 2) Env: MAMUTE_TIER_LIMITS_JSON.
    tier_env_limit = _limit_from_tier_entitlements(
        project,
        _parse_tier_entitlement_limits(settings.tier_limits_json),
    )
    if tier_env_limit is not None:
        return tier_env_limit

    # 3) DB (tier.detalhes) como fallback persistido.
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

    # 4) Default.
    return max(0, int(settings.chatbot_default_monthly_limit))


def resolve_weekly_limit(project: ChatProject) -> Optional[int]:
    """Weekly IA limit for a project. Optional: None means no weekly cap.

    Precedência: MAMUTE_TIER_LIMITS_JSON (env) > tier.detalhes (DB), na chave
    ``qtd_consultas_ia_semana``. Tier sem a chave → sem limite semanal (só o
    mensal vale), preservando o comportamento atual.
    """

    settings = get_settings()

    tier_limits = _parse_tier_entitlement_limits(settings.tier_limits_json)
    for key in (project.tier_slug, project.product_id):
        if not key or key not in tier_limits:
            continue
        entry = tier_limits[key]
        if not isinstance(entry, Mapping) or "qtd_consultas_ia_semana" not in entry:
            continue
        try:
            return max(0, int(entry["qtd_consultas_ia_semana"]))
        except (TypeError, ValueError) as exc:
            raise ChatQuotaConfigError(
                f"Limite 'qtd_consultas_ia_semana' inválido para o tier {key!r}."
            ) from exc

    raw = project.tier_details.get("qtd_consultas_ia_semana")
    if raw is None:
        return None
    try:
        return max(0, int(raw))
    except (TypeError, ValueError) as exc:
        raise ChatQuotaConfigError(
            f"Valor inválido de qtd_consultas_ia_semana para o tier {project.tier_slug!r}."
        ) from exc


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


def _weekly_usage_count(session: Session, project_id: int, week_start: date) -> int:
    """Consultas contadas na semana corrente (por data de criação).

    Usa ``date(created_at)`` (portável SQLite/Postgres). Em Postgres a truncagem
    usa o fuso do servidor — na virada domingo→segunda pode haver diferença de
    poucas horas; aceitável para um throttle semanal.
    """

    stmt = text(
        """
        SELECT COUNT(*)
        FROM chatbot_usage
        WHERE projeto_id = :project_id
          AND date(created_at) >= :week_start
          AND status IN :statuses
        """
    ).bindparams(bindparam("statuses", expanding=True))
    return int(
        session.execute(
            stmt,
            {
                "project_id": project_id,
                "week_start": week_start,
                "statuses": list(COUNTED_USAGE_STATUSES),
            },
        ).scalar_one()
        or 0
    )


def _make_window(limit: int, used: int, reset_at: datetime) -> ChatQuotaWindow:
    return ChatQuotaWindow(
        limit=limit,
        used=used,
        remaining=max(0, limit - used),
        reset_at=reset_at,
        limit_reached=used >= limit,
    )


def _pick_binding(
    weekly: Optional[ChatQuotaWindow], monthly: ChatQuotaWindow
) -> ChatQuotaWindow:
    """Janela que 'trava primeiro': a estourada (semanal tem prioridade), senão
    a de menor folga (empate → semanal, que reseta mais cedo)."""

    if weekly is not None and weekly.limit_reached:
        return weekly
    if monthly.limit_reached:
        return monthly
    if weekly is not None and weekly.remaining <= monthly.remaining:
        return weekly
    return monthly


def _compose_quota(
    weekly: Optional[ChatQuotaWindow], monthly: ChatQuotaWindow
) -> ChatQuotaResponse:
    binding = _pick_binding(weekly, monthly)
    return ChatQuotaResponse(
        enabled=True,
        limit=binding.limit,
        used=binding.used,
        remaining=binding.remaining,
        reset_at=binding.reset_at,
        limit_reached=binding.limit_reached,
        weekly=weekly,
        monthly=monthly,
    )


def _resolve_quota_windows(
    session: Session, project: ChatProject
) -> tuple[Optional[ChatQuotaWindow], ChatQuotaWindow]:
    period_start = current_period_start()
    month_limit = resolve_monthly_limit(project)
    month_used = _usage_count(session, project.id, period_start)
    monthly = _make_window(month_limit, month_used, next_period_start(period_start))

    weekly: Optional[ChatQuotaWindow] = None
    week_limit = resolve_weekly_limit(project)
    if week_limit is not None:
        week_start = current_week_start()
        week_used = _weekly_usage_count(session, project.id, week_start)
        weekly = _make_window(week_limit, week_used, next_week_start(week_start))
    return weekly, monthly


def get_chat_quota(session: Session, email: str) -> ChatQuotaResponse:
    """Return quota status for an authenticated project."""

    settings = get_settings()
    if not settings.chatbot_quota_enabled:
        return disabled_quota_response()

    project = _load_project(session, email)
    weekly, monthly = _resolve_quota_windows(session, project)
    return _compose_quota(weekly, monthly)


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
    if not settings.chatbot_quota_enabled:
        return ChatUsageStart(
            usage_id=None,
            quota=disabled_quota_response(),
        )

    project = _load_project(session, email, lock_for_update=True)
    weekly, monthly = _resolve_quota_windows(session, project)
    if weekly is not None and weekly.limit_reached:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Limite semanal de consultas IA atingido para seu plano "
                f"({weekly.used}/{weekly.limit}). A cota reseta na segunda-feira."
            ),
        )
    if monthly.limit_reached:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Limite mensal de consultas IA atingido para seu plano "
                f"({monthly.used}/{monthly.limit})."
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

    bumped_monthly = _make_window(monthly.limit, monthly.used + 1, monthly.reset_at)
    bumped_weekly = (
        _make_window(weekly.limit, weekly.used + 1, weekly.reset_at)
        if weekly is not None
        else None
    )
    return ChatUsageStart(
        usage_id=int(row[0]) if row else None,
        quota=_compose_quota(bumped_weekly, bumped_monthly),
    )


def compute_cost_usd(
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    input_usd_per_1m: float,
    output_usd_per_1m: float,
) -> Optional[float]:
    """Custo em US$ a partir dos tokens e do preço por 1M. None se sem tokens."""

    prompt = prompt_tokens or 0
    completion = completion_tokens or 0
    if prompt == 0 and completion == 0:
        return None
    cost = prompt / 1_000_000 * input_usd_per_1m + completion / 1_000_000 * output_usd_per_1m
    return round(cost, 6)


def _cost_for_usage(
    session: Session,
    usage_id: int,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
) -> Optional[float]:
    """Busca o preço do modelo da linha e calcula o custo (fail-soft => None)."""

    if prompt_tokens is None and completion_tokens is None:
        return None
    row = session.execute(
        text("SELECT model FROM chatbot_usage WHERE id = :id"), {"id": usage_id}
    ).first()
    model = row[0] if row else None
    if not model:
        return None
    pricing = session.execute(
        text(
            "SELECT input_usd_per_1m, output_usd_per_1m "
            "FROM model_pricing WHERE model = :model"
        ),
        {"model": model},
    ).first()
    if pricing is None:
        return None
    return compute_cost_usd(
        prompt_tokens, completion_tokens, float(pricing[0]), float(pricing[1])
    )


def mark_chat_usage(
    session: Session,
    usage_id: Optional[int],
    *,
    status_value: str,
    answer_chars: int = 0,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
) -> None:
    """Update the status of a previously reserved usage row (+ tokens/custo)."""

    if usage_id is None:
        return
    cost_usd = _cost_for_usage(session, usage_id, prompt_tokens, completion_tokens)
    session.execute(
        text(
            """
            UPDATE chatbot_usage
            SET status = :status,
                answer_chars = :answer_chars,
                prompt_tokens = COALESCE(:prompt_tokens, prompt_tokens),
                completion_tokens = COALESCE(:completion_tokens, completion_tokens),
                cost_usd = COALESCE(:cost_usd, cost_usd),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :usage_id
            """
        ),
        {
            "usage_id": usage_id,
            "status": status_value,
            "answer_chars": max(0, answer_chars),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost_usd,
        },
    )
    session.commit()


__all__ = [
    "ChatQuotaConfigError",
    "ChatUsageStart",
    "compute_cost_usd",
    "current_period_start",
    "current_week_start",
    "disabled_quota_response",
    "get_chat_quota",
    "mark_chat_usage",
    "next_week_start",
    "resolve_monthly_limit",
    "resolve_weekly_limit",
    "start_chat_usage",
]
