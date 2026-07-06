"""Cobertura do banco: serve o relatório já computado pela rotina diária.

O cálculo (proposições, discursos, votações, parlamentares — pesado ao vivo) mora
em mamute_scrappers.scripts.refresh_admin_caches (04h) e é gravado como JSON em
coverage_snapshot. Aqui só lemos a linha mais recente — resposta instantânea.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

# Payload "vazio" enquanto a rotina ainda não rodou (deploy novo). A UI mostra
# um aviso e o número volta assim que o job das 04h (ou manual) preencher.
_PENDING: dict[str, Any] = {
    "pending": True,
    "computed_at": None,
    "kpis": {},
    "proposicoes": {"camara": [], "senado": [], "nota_superset": ""},
    "discursos": {"camara": [], "senado": [], "nota": ""},
    "votacoes": {"camara": [], "senado": [], "nota": ""},
    "parlamentares": {},
    "consolidado": [],
}


def db_coverage(db: Session) -> dict[str, Any]:
    try:
        row = db.execute(
            text(
                "SELECT payload, computed_at FROM coverage_snapshot "
                "ORDER BY computed_at DESC LIMIT 1"
            )
        ).first()
    except SQLAlchemyError:
        db.rollback()
        return dict(_PENDING)

    if row is None:
        return dict(_PENDING)

    payload = row[0]
    if isinstance(payload, str):  # SQLite/JSON-como-texto
        payload = json.loads(payload)
    payload = dict(payload)
    payload["pending"] = False
    computed_at = row[1]
    payload["computed_at"] = (
        computed_at.isoformat() if isinstance(computed_at, datetime) else computed_at
    )
    return payload
