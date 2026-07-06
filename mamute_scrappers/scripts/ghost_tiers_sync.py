"""Sincroniza NOME e PREÇO MENSAL dos tiers a partir do Ghost (fonte da verdade).

O painel admin mostra `tier_name_debug` (título do plano) e `detalhes.preco_mensal`
(base da margem). Ambos passam a vir do Ghost Admin API — o `product_id` local já é
o id do tier no Ghost (via `member.subscriptions[].tier.id`); o tier gratuito casa
por `type == "free"` (product_id local = "free").

Roda no container dos scrappers (tem GHOST_API_KEY/GHOST_ADMIN_URL). É agendado
diariamente e também dá pra rodar na mão:

    python -m mamute_scrappers.scripts.ghost_tiers_sync

Reaproveita o mesmo esquema de token do create_users (JWT HS256, aud "/admin/").
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable

import jwt

logger = logging.getLogger("ghost_tiers_sync")

TIERS_PATH = "/tiers/?include=monthly_price&limit=all"


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


def parse_ghost_tiers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extrai [{product_id, name, monthly_price(R$)}] da resposta do Admin API.
    product_id casa com o tier local: 'free' para o gratuito, senão o id do Ghost.
    """
    out: list[dict[str, Any]] = []
    for tier in payload.get("tiers", []) or []:
        is_free = tier.get("type") == "free"
        product_id = "free" if is_free else tier.get("id")
        if not product_id:
            continue
        out.append(
            {
                "product_id": product_id,
                "name": (tier.get("name") or "").strip(),
                "monthly_price": _to_reais(tier.get("monthly_price")),
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


def sync_tiers(session: Any, ghost_tiers: list[dict[str, Any]]) -> list[str]:
    """Atualiza tier_name_debug + detalhes.preco_mensal casando por product_id.
    Import do model é lazy (mamute_scrappers.db.engine exige DATABASE_URL no import)."""
    from mamute_scrappers.db.models.project import Tiers

    updated: list[str] = []
    for gt in ghost_tiers:
        tier = (
            session.query(Tiers)
            .filter(Tiers.product_id == gt["product_id"], Tiers.deleted_at.is_(None))
            .one_or_none()
        )
        if tier is None:
            logger.info("Sem tier local para product_id=%s (%s)", gt["product_id"], gt["name"])
            continue
        if gt["name"]:
            tier.tier_name_debug = gt["name"]
        detalhes = dict(tier.detalhes or {})
        detalhes["preco_mensal"] = gt["monthly_price"]
        tier.detalhes = detalhes
        updated.append(gt["product_id"])
    session.commit()
    return updated


def run(session: Any, http_get: Callable[..., Any]) -> list[str]:
    api_key = os.getenv("GHOST_API") or os.getenv("GHOST_API_KEY")
    admin_url = os.getenv("GHOST_ADMIN_URL")
    if not api_key or not admin_url:
        raise RuntimeError(
            "GHOST_API_KEY/GHOST_ADMIN_URL ausentes — sync de tiers do Ghost pulado."
        )
    token = generate_admin_token(api_key)
    ghost_tiers = fetch_ghost_tiers(admin_url, token, http_get)
    updated = sync_tiers(session, ghost_tiers)
    logger.info("Ghost tiers sincronizados (%s): %s", len(updated), updated)
    return updated


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
