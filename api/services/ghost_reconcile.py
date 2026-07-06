"""Reconciliação Ghost Admin API -> tiers/projetos locais."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import requests
from sqlalchemy.orm import Session

try:
    from ..db.models.project import Tiers
    from .ghost_admin import (
        fetch_ghost_members,
        fetch_ghost_tiers,
        generate_admin_token,
        get_ghost_admin_settings,
    )
    from .ghost_member_sync import sync_member_project
except (ImportError, ValueError):  # pragma: no cover - caminho Docker/top-level.
    from db.models.project import Tiers
    from services.ghost_admin import (
        fetch_ghost_members,
        fetch_ghost_tiers,
        generate_admin_token,
        get_ghost_admin_settings,
    )
    from services.ghost_member_sync import sync_member_project


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GhostReconcileResult:
    action: str
    reason: str | None = None
    tiers_updated: int = 0
    members_seen: int = 0
    projects_created: int = 0
    projects_updated: int = 0
    members_ignored: int = 0


def _coerce_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _to_reais(monthly_price: Any) -> float:
    if isinstance(monthly_price, (int, float)):
        return round(monthly_price / 100, 2)
    return 0.0


def _ghost_tier_product_id(tier: Mapping[str, Any]) -> str | None:
    if tier.get("type") == "free":
        return "free"
    tier_id = tier.get("id")
    return tier_id.strip() if isinstance(tier_id, str) and tier_id.strip() else None


def _tier_lookup_keys(tier: Tiers) -> set[str]:
    keys = {tier.product_id}
    detalhes = _coerce_mapping(getattr(tier, "detalhes", None))
    ghost = _coerce_mapping(detalhes.get("ghost"))
    for key in ("slug", "target_tier_id", "source_tier_id"):
        value = ghost.get(key)
        if isinstance(value, str) and value.strip():
            keys.add(value.strip())
    return keys


def _find_local_tier(tier_map: dict[str, Tiers], ghost_tier: Mapping[str, Any]) -> Tiers | None:
    for key in (
        _ghost_tier_product_id(ghost_tier),
        ghost_tier.get("id"),
        ghost_tier.get("slug"),
    ):
        if isinstance(key, str) and key.strip() and key.strip() in tier_map:
            return tier_map[key.strip()]
    return None


def sync_ghost_tiers(session: Session, ghost_tiers: list[dict[str, Any]]) -> list[str]:
    local_tiers = session.query(Tiers).filter(Tiers.deleted_at.is_(None)).all()
    tier_map = {key: tier for tier in local_tiers for key in _tier_lookup_keys(tier)}

    updated: list[str] = []
    for ghost_tier in ghost_tiers:
        tier = _find_local_tier(tier_map, ghost_tier)
        if tier is None:
            continue

        name = ghost_tier.get("name")
        if isinstance(name, str) and name.strip():
            tier.tier_name_debug = name.strip()

        detalhes = dict(_coerce_mapping(tier.detalhes))
        detalhes["preco_mensal"] = _to_reais(ghost_tier.get("monthly_price"))
        ghost = dict(_coerce_mapping(detalhes.get("ghost")))
        slug = ghost_tier.get("slug")
        ghost_tier_id = ghost_tier.get("id")
        ghost_type = ghost_tier.get("type")
        if isinstance(slug, str) and slug.strip():
            ghost["slug"] = slug.strip()
        if isinstance(ghost_tier_id, str) and ghost_tier_id.strip():
            ghost["target_tier_id"] = ghost_tier_id.strip()
        if isinstance(ghost_type, str) and ghost_type.strip():
            ghost["type"] = ghost_type.strip()
        detalhes["ghost"] = ghost
        tier.detalhes = detalhes
        product_id = _ghost_tier_product_id(ghost_tier)
        if product_id:
            updated.append(product_id)

    session.commit()
    return updated


def sync_ghost_members(
    session: Session,
    ghost_members: list[dict[str, Any]],
) -> tuple[int, int, int]:
    created = 0
    updated = 0
    ignored = 0

    for member in ghost_members:
        result = sync_member_project(session, member)
        if result.action == "created":
            created += 1
        elif result.action == "updated":
            updated += 1
        else:
            ignored += 1

    return created, updated, ignored


def run_ghost_reconciliation(
    session: Session,
    http_get: Callable[..., Any] = requests.get,
) -> GhostReconcileResult:
    settings = get_ghost_admin_settings()
    if settings is None:
        return GhostReconcileResult(
            action="skipped",
            reason="missing_ghost_admin_config",
        )

    token = generate_admin_token(settings.api_key)
    ghost_tiers = fetch_ghost_tiers(settings.admin_url, token, http_get)
    tiers_updated = sync_ghost_tiers(session, ghost_tiers)

    ghost_members = fetch_ghost_members(settings.admin_url, token, http_get)
    projects_created, projects_updated, members_ignored = sync_ghost_members(
        session,
        ghost_members,
    )

    result = GhostReconcileResult(
        action="synced",
        tiers_updated=len(tiers_updated),
        members_seen=len(ghost_members),
        projects_created=projects_created,
        projects_updated=projects_updated,
        members_ignored=members_ignored,
    )
    logger.info("Reconciliação Ghost concluída: %s", result)
    return result


__all__ = [
    "GhostReconcileResult",
    "run_ghost_reconciliation",
    "sync_ghost_members",
    "sync_ghost_tiers",
]
