"""Seed sem regressão: copia o total global (qtd_termos) para o limite de cada
casa (qtd_termos_camara / qtd_termos_senado), quando ausentes. Idempotente.

Contexto: o limite de parlamentares monitorados deixou de ser um total global e
passou a ser por casa (deputado/senador). Para não quebrar clientes existentes
no deploy, cada casa herda o total global atual. Números finais por casa são
ajustados depois no painel admin.

Uso: DATABASE_URL=... python -m scripts.seed_per_house_favorite_limits
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

_HOUSE_KEYS = ("qtd_termos_camara", "qtd_termos_senado")


def seed_per_house_from_global(session: Session) -> list[str]:
    rows = (
        session.execute(
            text(
                "select id, product_id, detalhes from tiers "
                "where deleted_at is null"
            )
        )
        .mappings()
        .all()
    )
    updated: list[str] = []
    for row in rows:
        current = (
            json.loads(row["detalhes"])
            if isinstance(row["detalhes"], str)
            else dict(row["detalhes"] or {})
        )
        global_limit = current.get("qtd_termos")
        if global_limit is None:
            continue
        changed = False
        for key in _HOUSE_KEYS:
            if key not in current:
                current[key] = global_limit
                changed = True
        if changed:
            session.execute(
                text("update tiers set detalhes = :d where id = :id"),
                {"d": json.dumps(current, ensure_ascii=False), "id": row["id"]},
            )
            updated.append(row["product_id"])
    session.commit()
    return updated


def main() -> None:
    from api.db.engine import SessionLocal  # reusa a engine da api

    session = SessionLocal()
    try:
        updated = seed_per_house_from_global(session)
        print(f"Tiers semeados por casa: {updated}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
