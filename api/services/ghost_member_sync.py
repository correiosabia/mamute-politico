"""Sincronização idempotente de membros Ghost com projetos locais."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    # Execução como pacote (api.services.*).
    from ..db.models.project import Projetos, Tiers
except (ImportError, ValueError):  # pragma: no cover - caminho Docker/top-level.
    from db.models.project import Projetos, Tiers


@dataclass(frozen=True)
class GhostMemberProjectSyncResult:
    """Resumo do que ocorreu ao processar um membro do Ghost."""

    action: str
    email: Optional[str] = None
    project_id: Optional[int] = None
    product_id: Optional[str] = None
    reason: Optional[str] = None


def sanitize_name(value: Optional[str], fallback: str) -> str:
    base = (value or fallback).strip().lower()
    if not base:
        base = fallback

    sanitized = "".join(char if char.isalnum() else "_" for char in base)
    sanitized = "_".join(filter(None, sanitized.split("_")))
    return sanitized or fallback


def generate_bot_name(email: str, name: Optional[str]) -> str:
    local_part = email.split("@", maxsplit=1)[0]
    base = sanitize_name(name, fallback=local_part)
    digest = hashlib.shake_256(email.encode("utf-8")).hexdigest(4)
    return f"{base}_{digest}"


def normalize_email(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def resolve_product_id(member: dict[str, Any]) -> str:
    if member.get("status") == "free":
        return "free"

    subscriptions = member.get("subscriptions") or []
    if subscriptions:
        tier_info = subscriptions[-1].get("tier") or {}
        return tier_info.get("id") or "free"

    tiers = member.get("tiers") or []
    if tiers:
        return tiers[-1].get("id") or "free"

    return "free"


def resolve_label(member: dict[str, Any]) -> Optional[str]:
    labels = member.get("labels") or []
    if not labels:
        return None
    return labels[0].get("slug")


def _get_tier_by_product_id(session: Session, product_id: str) -> Optional[Tiers]:
    stmt = select(Tiers).where(
        Tiers.product_id == product_id,
        Tiers.deleted_at.is_(None),
    )
    return session.execute(stmt).scalar_one_or_none()


def _get_project_by_email(session: Session, email: str) -> Optional[Projetos]:
    stmt = select(Projetos).where(Projetos.email == email)
    return session.execute(stmt).scalar_one_or_none()


def sync_member_project(
    session: Session,
    current_member: dict[str, Any],
    previous_member: Optional[dict[str, Any]] = None,
) -> GhostMemberProjectSyncResult:
    """Cria, atualiza ou reativa o projeto correspondente ao membro Ghost."""

    email = normalize_email(current_member.get("email"))
    if email is None:
        return GhostMemberProjectSyncResult(action="ignored", reason="missing_email")

    product_id = resolve_product_id(current_member)
    tier = _get_tier_by_product_id(session, product_id)
    if tier is None:
        return GhostMemberProjectSyncResult(
            action="ignored",
            email=email,
            product_id=product_id,
            reason="missing_tier",
        )

    previous_email = normalize_email((previous_member or {}).get("email"))
    project = _get_project_by_email(session, email)
    previous_project = None
    if project is None and previous_email and previous_email != email:
        previous_project = _get_project_by_email(session, previous_email)
        project = previous_project
    elif project is not None and previous_email and previous_email != email:
        previous_project = _get_project_by_email(session, previous_email)
        if previous_project is not None and previous_project.id != project.id:
            previous_project.deleted_at = datetime.now(timezone.utc)

    created = False
    if project is None:
        project = Projetos(
            nome=generate_bot_name(email, current_member.get("name")),
            email=email,
        )
        session.add(project)
        created = True

    project.email = email
    project.cliente = product_id
    project.tier_id = tier.id
    project.qtd_termos = tier.qtd_termos or 0
    project.tag_ghost = resolve_label(current_member)
    project.deleted_at = None

    session.commit()
    session.refresh(project)

    return GhostMemberProjectSyncResult(
        action="created" if created else "updated",
        email=email,
        project_id=int(project.id),
        product_id=product_id,
    )


def soft_delete_member_project(
    session: Session,
    member: dict[str, Any],
) -> GhostMemberProjectSyncResult:
    """Marca o projeto do membro como removido sem apagar histórico."""

    email = normalize_email(member.get("email"))
    if email is None:
        return GhostMemberProjectSyncResult(action="ignored", reason="missing_email")

    project = _get_project_by_email(session, email)
    if project is None:
        return GhostMemberProjectSyncResult(
            action="ignored",
            email=email,
            reason="missing_project",
        )

    project.deleted_at = datetime.now(timezone.utc)
    session.commit()

    return GhostMemberProjectSyncResult(
        action="soft_deleted",
        email=email,
        project_id=int(project.id),
    )


__all__ = [
    "GhostMemberProjectSyncResult",
    "generate_bot_name",
    "normalize_email",
    "resolve_label",
    "resolve_product_id",
    "sanitize_name",
    "soft_delete_member_project",
    "sync_member_project",
]
