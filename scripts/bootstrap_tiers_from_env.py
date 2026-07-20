"""Copia MAMUTE_TIER_LIMITS_JSON para tiers.detalhes (idempotente).

Uso: DATABASE_URL=... MAMUTE_TIER_LIMITS_JSON=... python -m scripts.bootstrap_tiers_from_env
"""
from __future__ import annotations

import json
import os
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

_KEYS = (
    "qtd_termos",
    "qtd_termos_camara",
    "qtd_termos_senado",
    "qtd_consultas_ia_mes",
)


def bootstrap_tiers_from_env(session: Session, raw_json: str) -> list[str]:
    payload: dict[str, Any] = json.loads(raw_json) if raw_json.strip() else {}
    updated: list[str] = []
    for product_id, entry in payload.items():
        if not isinstance(entry, dict):
            continue
        row = session.execute(
            text(
                "select id, detalhes from tiers where product_id = :pid "
                "and deleted_at is null"
            ),
            {"pid": product_id},
        ).mappings().first()
        if row is None:
            continue
        current = (
            json.loads(row["detalhes"])
            if isinstance(row["detalhes"], str)
            else dict(row["detalhes"] or {})
        )
        changed = False
        for key in _KEYS:
            if key in entry and current.get(key) != entry[key]:
                current[key] = entry[key]
                changed = True
        if changed:
            session.execute(
                text("update tiers set detalhes = :d where id = :id"),
                {"d": json.dumps(current, ensure_ascii=False), "id": row["id"]},
            )
            updated.append(product_id)
    session.commit()
    return updated


def main() -> None:
    from api.db.engine import SessionLocal  # reusa a engine da api

    raw = os.getenv("MAMUTE_TIER_LIMITS_JSON", "")
    session = SessionLocal()
    try:
        updated = bootstrap_tiers_from_env(session, raw)
        print(f"Tiers atualizados: {updated}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
