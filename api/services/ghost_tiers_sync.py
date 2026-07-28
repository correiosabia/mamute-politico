"""Espelha o catálogo de planos do Ghost na tabela `tiers`.

O Ghost é a fonte da verdade do catálogo: nome, preço, slug e status (ativo ou
arquivado). Os limites de cada plano pertencem ao painel admin e o sync nunca os
sobrescreve; no máximo herda os de um plano existente quando um plano novo
aparece no Ghost.

Regras (CS-28):

- plano no Ghost sem par local → cria herdando os limites do plano de preço mais
  próximo, marcado com ``pending_review`` para o painel destacar;
- plano arquivado no Ghost → marca ``ghost.active = false``. Só sai do ar
  (``deleted_at``) se não houver projeto ativo; com assinantes, segue atendendo;
- plano reativado no Ghost → volta a valer aqui;
- plano local sem par no Ghost → marcado como órfão, nunca apagado.

Este módulo tem um espelho em ``mamute_scrappers/scripts/ghost_tiers_sync.py``,
que roda no cron das 04h15 e no startup do container dos scrappers. Ao mudar uma
regra aqui, mudar lá também.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Optional

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    from ..db.models.project import Projetos, Tiers
    from .ghost_admin import (
        fetch_ghost_tiers,
        generate_admin_token,
        get_ghost_admin_settings,
    )
except ImportError:  # execução dentro de api/
    from db.models.project import Projetos, Tiers
    from services.ghost_admin import (
        fetch_ghost_tiers,
        generate_admin_token,
        get_ghost_admin_settings,
    )

logger = logging.getLogger(__name__)

# Chaves de limite que pertencem ao painel admin. O sync só as escreve ao criar
# um plano novo (herança); em plano existente, jamais.
ENTITLEMENT_KEYS = (
    "qtd_termos",
    "qtd_termos_camara",
    "qtd_termos_senado",
    "qtd_consultas_ia_mes",
    "qtd_consultas_ia_semana",
    "qtd_email",
    "periodicidade_email",
    "orgao",
)


class GhostTiersSyncError(RuntimeError):
    """Configuração ausente ou Ghost indisponível."""


@dataclass
class TierSyncSummary:
    created: list[dict[str, Any]] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    archived: list[dict[str, Any]] = field(default_factory=list)
    reactivated: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "updated": self.updated,
            "archived": self.archived,
            "reactivated": self.reactivated,
            "orphans": self.orphans,
        }

    @property
    def changed(self) -> bool:
        return bool(
            self.created or self.archived or self.reactivated or self.orphans
        )


def _coerce_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _to_reais(monthly_price: Any) -> float:
    """Ghost devolve monthly_price em centavos; free vem nulo → R$ 0,00."""
    if isinstance(monthly_price, (int, float)):
        return round(monthly_price / 100, 2)
    return 0.0


def normalize_ghost_tiers(raw_tiers: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Achata a resposta do Admin API no formato usado pelo sync.

    ``product_id`` casa com o tier local: ``"free"`` para o gratuito (o membro
    sem assinatura não traz id de tier), senão o id do Ghost.
    """
    out: list[dict[str, Any]] = []
    for tier in raw_tiers:
        if not isinstance(tier, Mapping):
            continue
        is_free = tier.get("type") == "free"
        product_id = "free" if is_free else tier.get("id")
        if not product_id:
            continue
        active = tier.get("active")
        out.append(
            {
                "product_id": str(product_id),
                "ghost_tier_id": tier.get("id"),
                "slug": tier.get("slug"),
                "type": tier.get("type"),
                "name": (tier.get("name") or "").strip(),
                "monthly_price": _to_reais(tier.get("monthly_price")),
                # Ghost sempre manda o campo; ausência é tratada como ativo para
                # não arquivar plano por engano.
                "active": True if active is None else bool(active),
            }
        )
    return out


def _tier_lookup_keys(tier: Tiers) -> set[str]:
    keys = {tier.product_id}
    ghost = _coerce_mapping(_coerce_mapping(tier.detalhes).get("ghost"))
    for key in ("slug", "target_tier_id", "source_tier_id"):
        value = ghost.get(key)
        if isinstance(value, str) and value.strip():
            keys.add(value.strip())
    return {key for key in keys if isinstance(key, str) and key.strip()}


def _find_local_tier(
    tier_map: Mapping[str, Tiers], ghost_tier: Mapping[str, Any]
) -> Optional[Tiers]:
    for key in (
        ghost_tier.get("product_id"),
        ghost_tier.get("ghost_tier_id"),
        ghost_tier.get("slug"),
    ):
        if isinstance(key, str) and key.strip() and key.strip() in tier_map:
            return tier_map[key.strip()]
    return None


def _active_project_count(session: Session, tier_id: Any) -> int:
    if tier_id is None:
        return 0
    stmt = select(Projetos.id).where(
        Projetos.tier_id == tier_id, Projetos.deleted_at.is_(None)
    )
    return len(session.execute(stmt).all())


def pick_inheritance_source(
    tiers: Iterable[Tiers], monthly_price: float
) -> Optional[Tiers]:
    """Plano do qual um plano novo herda limites.

    Regra: o plano ativo mais caro entre os que custam até o preço do novo. Se
    nenhum couber (o novo é o mais barato de todos), herda do mais barato
    existente. Determinístico e explicável para quem olha o painel depois.
    """
    candidates = [
        tier
        for tier in tiers
        if tier.deleted_at is None
        and any(key in _coerce_mapping(tier.detalhes) for key in ENTITLEMENT_KEYS)
    ]
    if not candidates:
        return None

    def price_of(tier: Tiers) -> float:
        raw = _coerce_mapping(tier.detalhes).get("preco_mensal")
        return float(raw) if isinstance(raw, (int, float)) else 0.0

    cheaper = [tier for tier in candidates if price_of(tier) <= monthly_price]
    if cheaper:
        return max(cheaper, key=lambda tier: (price_of(tier), str(tier.product_id)))
    return min(candidates, key=lambda tier: (price_of(tier), str(tier.product_id)))


def _inherited_details(source: Optional[Tiers]) -> dict[str, Any]:
    if source is None:
        return {}
    source_details = _coerce_mapping(source.detalhes)
    return {
        key: source_details[key] for key in ENTITLEMENT_KEYS if key in source_details
    }


def _apply_ghost_block(detalhes: dict[str, Any], ghost_tier: Mapping[str, Any]) -> None:
    ghost = _coerce_mapping(detalhes.get("ghost"))
    if ghost_tier.get("slug"):
        ghost["slug"] = ghost_tier["slug"]
    if ghost_tier.get("ghost_tier_id"):
        ghost["target_tier_id"] = ghost_tier["ghost_tier_id"]
    if ghost_tier.get("type"):
        ghost["type"] = ghost_tier["type"]
    ghost["active"] = bool(ghost_tier.get("active", True))
    ghost.pop("orphan", None)
    detalhes["ghost"] = ghost


def sync_tiers(
    session: Session,
    ghost_tiers: list[dict[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> TierSyncSummary:
    """Aplica o catálogo do Ghost na tabela `tiers`. Idempotente."""
    moment = now or datetime.now(timezone.utc)
    summary = TierSyncSummary()

    local_tiers = list(session.execute(select(Tiers)).scalars().all())
    tier_map: dict[str, Tiers] = {}
    for tier in local_tiers:
        for key in _tier_lookup_keys(tier):
            # Linha viva ganha da soft-deletada quando as chaves colidem (é o
            # caso do gratuito duplicado que existiu em produção).
            existing = tier_map.get(key)
            if existing is None or (
                existing.deleted_at is not None and tier.deleted_at is None
            ):
                tier_map[key] = tier

    matched: set[int] = set()

    for ghost_tier in ghost_tiers:
        tier = _find_local_tier(tier_map, ghost_tier)
        is_active = bool(ghost_tier.get("active", True))

        if tier is None:
            source = pick_inheritance_source(local_tiers, ghost_tier["monthly_price"])
            detalhes = _inherited_details(source)
            detalhes["preco_mensal"] = ghost_tier["monthly_price"]
            _apply_ghost_block(detalhes, ghost_tier)
            detalhes["ghost"]["pending_review"] = True
            if source is not None:
                detalhes["ghost"]["herdado_de"] = source.product_id
            tier = Tiers(
                tier_name_debug=ghost_tier["name"] or ghost_tier["product_id"],
                product_id=ghost_tier["product_id"],
                detalhes=detalhes,
                deleted_at=None if is_active else moment,
            )
            session.add(tier)
            local_tiers.append(tier)
            for key in _tier_lookup_keys(tier):
                tier_map.setdefault(key, tier)
            summary.created.append(
                {
                    "product_id": tier.product_id,
                    "name": tier.tier_name_debug,
                    "herdado_de": detalhes["ghost"].get("herdado_de"),
                    "active": is_active,
                }
            )
            continue

        matched.add(id(tier))

        if ghost_tier["name"]:
            tier.tier_name_debug = ghost_tier["name"]
        detalhes = _coerce_mapping(tier.detalhes)
        detalhes["preco_mensal"] = ghost_tier["monthly_price"]
        _apply_ghost_block(detalhes, ghost_tier)

        if is_active:
            if tier.deleted_at is not None:
                tier.deleted_at = None
                detalhes["ghost"].pop("archived_with_subscribers", None)
                summary.reactivated.append(tier.product_id)
        else:
            subscribers = _active_project_count(session, tier.id)
            if subscribers:
                # "Arquivado mantém": quem já assina continua atendido.
                detalhes["ghost"]["archived_with_subscribers"] = True
            else:
                detalhes["ghost"].pop("archived_with_subscribers", None)
                if tier.deleted_at is None:
                    tier.deleted_at = moment
            if tier.deleted_at is not None or subscribers:
                summary.archived.append(
                    {
                        "product_id": tier.product_id,
                        "name": tier.tier_name_debug,
                        "assinantes": subscribers,
                    }
                )

        tier.detalhes = detalhes
        summary.updated.append(tier.product_id)

    for tier in local_tiers:
        if id(tier) in matched or tier.deleted_at is not None:
            continue
        if any(entry["product_id"] == tier.product_id for entry in summary.created):
            continue
        detalhes = _coerce_mapping(tier.detalhes)
        ghost = _coerce_mapping(detalhes.get("ghost"))
        ghost["orphan"] = True
        detalhes["ghost"] = ghost
        tier.detalhes = detalhes
        summary.orphans.append(tier.product_id)

    session.commit()
    return summary


def run_sync(
    session: Session,
    http_get: Callable[..., Any] = requests.get,
    *,
    now: Optional[datetime] = None,
) -> TierSyncSummary:
    """Busca o catálogo no Ghost e aplica. Levanta se faltar configuração."""
    settings = get_ghost_admin_settings()
    if settings is None:
        raise GhostTiersSyncError(
            "GHOST_API/GHOST_ADMIN_URL ausentes — sync de tiers indisponível."
        )
    token = generate_admin_token(settings.api_key)
    raw = fetch_ghost_tiers(settings.admin_url, token, http_get)
    summary = sync_tiers(session, normalize_ghost_tiers(raw), now=now)
    logger.info("Ghost tiers sincronizados: %s", summary.as_dict())
    return summary


__all__ = [
    "ENTITLEMENT_KEYS",
    "GhostTiersSyncError",
    "TierSyncSummary",
    "normalize_ghost_tiers",
    "pick_inheritance_source",
    "run_sync",
    "sync_tiers",
]
