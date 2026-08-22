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

Roda no container dos scrappers (tem GHOST_API/GHOST_ADMIN_URL): cron das 04h15
e reconciliação de startup. Também dá para rodar na mão:

    python -m mamute_scrappers.scripts.ghost_tiers_sync

Espelho deste módulo em ``api/services/ghost_tiers_sync.py``, usado pelo botão
"Sincronizar agora" do painel admin. Ao mudar uma regra aqui, mudar lá também.
Reaproveita o mesmo esquema de token do create_users (JWT HS256, aud "/admin/").
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

import jwt

logger = logging.getLogger("ghost_tiers_sync")

TIERS_PATH = "/tiers/?include=monthly_price&limit=all"

# Chaves de limite que pertencem ao painel admin. O sync só as escreve ao criar
# um plano novo (herança); em plano existente, jamais.
ENTITLEMENT_KEYS = (
    "qtd_termos",
    "qtd_termos_camara",
    "qtd_termos_senado",
    "qtd_candidatos",
    "qtd_consultas_ia_mes",
    "qtd_consultas_ia_semana",
    "qtd_email",
    "periodicidade_email",
    "orgao",
)


def generate_admin_token(api_key: str) -> str:
    """JWT do Ghost Admin API. `api_key` no formato '<kid>:<secret_hex>'."""
    try:
        kid, secret = api_key.split(":")
    except ValueError as exc:  # pragma: no cover - erro de config
        raise RuntimeError("GHOST_API inválido. Esperado '<key>:<secret>'.") from exc
    iat = int(datetime.now(timezone.utc).timestamp())
    return jwt.encode(
        {"iat": iat, "exp": iat + 5 * 60, "aud": "/admin/"},
        bytes.fromhex(secret),
        algorithm="HS256",
        headers={"alg": "HS256", "typ": "JWT", "kid": kid},
    )


def _to_reais(monthly_price: Any) -> float:
    """Ghost devolve monthly_price em centavos; free vem nulo → R$ 0,00."""
    if isinstance(monthly_price, (int, float)):
        return round(monthly_price / 100, 2)
    return 0.0


def _coerce_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def parse_ghost_tiers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extrai o catálogo da resposta do Admin API.

    ``product_id`` casa com o tier local: 'free' para o gratuito, senão o id do
    Ghost. ``active`` distingue plano vivo de plano arquivado.
    """
    out: list[dict[str, Any]] = []
    for tier in payload.get("tiers", []) or []:
        is_free = tier.get("type") == "free"
        product_id = "free" if is_free else tier.get("id")
        if not product_id:
            continue
        active = tier.get("active")
        out.append(
            {
                "product_id": product_id,
                "ghost_tier_id": tier.get("id"),
                "slug": tier.get("slug"),
                "type": tier.get("type"),
                "name": (tier.get("name") or "").strip(),
                "monthly_price": _to_reais(tier.get("monthly_price")),
                # Ausência do campo é tratada como ativo: nunca arquivar por
                # falta de informação.
                "active": True if active is None else bool(active),
            }
        )
    return out


def fetch_ghost_tiers(
    admin_url: str, token: str, http_get: Callable[..., Any]
) -> list[dict[str, Any]]:
    url = f"{admin_url.rstrip('/')}{TIERS_PATH}"
    resp = http_get(url, headers={"Authorization": f"Ghost {token}"}, timeout=30)
    resp.raise_for_status()
    return parse_ghost_tiers(resp.json())


def _tier_lookup_keys(tier: Any) -> set[str]:
    keys = {tier.product_id}
    detalhes = tier.detalhes if isinstance(tier.detalhes, dict) else {}
    ghost = _coerce_mapping(detalhes.get("ghost"))
    for key in ("slug", "target_tier_id", "source_tier_id"):
        value = ghost.get(key)
        if isinstance(value, str) and value.strip():
            keys.add(value.strip())
    return {key for key in keys if isinstance(key, str) and key.strip()}


def _find_local_tier(tier_map: dict[str, Any], ghost_tier: dict[str, Any]) -> Any:
    for key in (
        ghost_tier.get("product_id"),
        ghost_tier.get("ghost_tier_id"),
        ghost_tier.get("slug"),
    ):
        if isinstance(key, str) and key.strip() and key.strip() in tier_map:
            return tier_map[key.strip()]
    return None


def pick_inheritance_source(tiers: list[Any], monthly_price: float) -> Any:
    """Plano do qual um plano novo herda limites.

    Regra: o plano ativo mais caro entre os que custam até o preço do novo. Se
    nenhum couber, herda do mais barato existente.
    """
    candidates = [
        tier
        for tier in tiers
        if tier.deleted_at is None
        and any(key in _coerce_mapping(tier.detalhes) for key in ENTITLEMENT_KEYS)
    ]
    if not candidates:
        return None

    def price_of(tier: Any) -> float:
        raw = _coerce_mapping(tier.detalhes).get("preco_mensal")
        return float(raw) if isinstance(raw, (int, float)) else 0.0

    cheaper = [tier for tier in candidates if price_of(tier) <= monthly_price]
    if cheaper:
        return max(cheaper, key=lambda tier: (price_of(tier), str(tier.product_id)))
    return min(candidates, key=lambda tier: (price_of(tier), str(tier.product_id)))


def _inherited_details(source: Any) -> dict[str, Any]:
    if source is None:
        return {}
    source_details = _coerce_mapping(source.detalhes)
    return {
        key: source_details[key] for key in ENTITLEMENT_KEYS if key in source_details
    }


def _apply_ghost_block(detalhes: dict[str, Any], ghost_tier: dict[str, Any]) -> None:
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
    session: Any,
    ghost_tiers: list[dict[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Aplica o catálogo do Ghost na tabela `tiers`. Idempotente.

    Import do model é lazy (mamute_scrappers.db.engine exige DATABASE_URL no
    import).
    """
    from mamute_scrappers.db.models.project import Projetos, Tiers

    moment = now or datetime.now(timezone.utc)
    summary: dict[str, Any] = {
        "created": [],
        "updated": [],
        "archived": [],
        "reactivated": [],
        "orphans": [],
    }

    local_tiers = list(session.query(Tiers).all())
    tier_map: dict[str, Any] = {}
    for tier in local_tiers:
        for key in _tier_lookup_keys(tier):
            # Linha viva ganha da soft-deletada quando as chaves colidem.
            existing = tier_map.get(key)
            if existing is None or (
                existing.deleted_at is not None and tier.deleted_at is None
            ):
                tier_map[key] = tier

    def _assinantes(tier: Any) -> int:
        if tier.id is None:
            return 0
        return (
            session.query(Projetos)
            .filter(Projetos.tier_id == tier.id, Projetos.deleted_at.is_(None))
            .count()
        )

    matched: set[int] = set()

    for gt in ghost_tiers:
        tier = _find_local_tier(tier_map, gt)
        is_active = bool(gt.get("active", True))

        if tier is None:
            source = pick_inheritance_source(local_tiers, gt["monthly_price"])
            detalhes = _inherited_details(source)
            detalhes["preco_mensal"] = gt["monthly_price"]
            _apply_ghost_block(detalhes, gt)
            detalhes["ghost"]["pending_review"] = True
            if source is not None:
                detalhes["ghost"]["herdado_de"] = source.product_id
            tier = Tiers(
                tier_name_debug=gt["name"] or gt["product_id"],
                product_id=gt["product_id"],
                detalhes=detalhes,
                deleted_at=None if is_active else moment,
            )
            session.add(tier)
            local_tiers.append(tier)
            for key in _tier_lookup_keys(tier):
                tier_map.setdefault(key, tier)
            summary["created"].append(
                {
                    "product_id": tier.product_id,
                    "name": tier.tier_name_debug,
                    "herdado_de": detalhes["ghost"].get("herdado_de"),
                    "active": is_active,
                }
            )
            logger.info(
                "Tier novo no Ghost: %s (%s) criado herdando de %s",
                gt["product_id"],
                gt["name"],
                detalhes["ghost"].get("herdado_de"),
            )
            continue

        matched.add(id(tier))

        if gt["name"]:
            tier.tier_name_debug = gt["name"]
        detalhes = _coerce_mapping(tier.detalhes)
        detalhes["preco_mensal"] = gt["monthly_price"]
        _apply_ghost_block(detalhes, gt)

        if is_active:
            if tier.deleted_at is not None:
                tier.deleted_at = None
                detalhes["ghost"].pop("archived_with_subscribers", None)
                summary["reactivated"].append(tier.product_id)
                logger.info("Tier reativado no Ghost: %s", tier.product_id)
        else:
            subscribers = _assinantes(tier)
            if subscribers:
                # "Arquivado mantém": quem já assina continua atendido.
                detalhes["ghost"]["archived_with_subscribers"] = True
            else:
                detalhes["ghost"].pop("archived_with_subscribers", None)
                if tier.deleted_at is None:
                    tier.deleted_at = moment
            if tier.deleted_at is not None or subscribers:
                summary["archived"].append(
                    {
                        "product_id": tier.product_id,
                        "name": tier.tier_name_debug,
                        "assinantes": subscribers,
                    }
                )
                logger.info(
                    "Tier arquivado no Ghost: %s (%s assinante(s))",
                    tier.product_id,
                    subscribers,
                )

        tier.detalhes = detalhes
        summary["updated"].append(tier.product_id)

    for tier in local_tiers:
        if id(tier) in matched or tier.deleted_at is not None:
            continue
        if any(entry["product_id"] == tier.product_id for entry in summary["created"]):
            continue
        detalhes = _coerce_mapping(tier.detalhes)
        ghost = _coerce_mapping(detalhes.get("ghost"))
        ghost["orphan"] = True
        detalhes["ghost"] = ghost
        tier.detalhes = detalhes
        summary["orphans"].append(tier.product_id)
        logger.warning("Tier local sem par no Ghost: %s", tier.product_id)

    session.commit()
    return summary


def run(session: Any, http_get: Callable[..., Any]) -> dict[str, Any]:
    api_key = os.getenv("GHOST_API") or os.getenv("GHOST_API_KEY")
    admin_url = os.getenv("GHOST_ADMIN_URL")
    if not api_key or not admin_url:
        raise RuntimeError(
            "GHOST_API_KEY/GHOST_ADMIN_URL ausentes — sync de tiers do Ghost pulado."
        )
    token = generate_admin_token(api_key)
    ghost_tiers = fetch_ghost_tiers(admin_url, token, http_get)
    summary = sync_tiers(session, ghost_tiers)
    logger.info(
        "Ghost tiers sincronizados: %s atualizados, %s criados, %s arquivados, "
        "%s reativados, %s órfãos",
        len(summary["updated"]),
        len(summary["created"]),
        len(summary["archived"]),
        len(summary["reactivated"]),
        len(summary["orphans"]),
    )
    return summary


def main() -> None:
    import requests

    from mamute_scrappers.db.session import get_session

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    session = get_session()
    try:
        run(session, requests.get)
    finally:
        session.close()


if __name__ == "__main__":
    main()
