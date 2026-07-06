"""Sincroniza model_pricing com os preços do OpenRouter.

Uso: DATABASE_URL=... python -m scripts.sync_model_pricing

O OpenRouter (GET /api/v1/models) devolve `pricing.prompt`/`.completion` em
US$ por TOKEN; convertemos para US$ por 1M tokens. A chave `model` é o id do
OpenRouter (ex.: 'google/gemini-2.5-flash'); garanta que ele bata com o
`settings.openai_model` gravado em chatbot_usage para o custo casar (ou mantenha
a linha 'seed' correspondente ao modelo em uso).
"""
from __future__ import annotations

import os
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def parse_openrouter_models(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Converte o payload do OpenRouter em linhas de model_pricing."""
    rows: list[dict[str, Any]] = []
    for model in payload.get("data", []) or []:
        model_id = model.get("id")
        pricing = model.get("pricing") or {}
        prompt = pricing.get("prompt")
        completion = pricing.get("completion")
        if not model_id or prompt is None or completion is None:
            continue
        try:
            input_per_1m = float(prompt) * 1_000_000
            output_per_1m = float(completion) * 1_000_000
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "model": model_id,
                "input_usd_per_1m": round(input_per_1m, 6),
                "output_usd_per_1m": round(output_per_1m, 6),
            }
        )
    return rows


def upsert_pricing(session: Session, rows: list[dict[str, Any]]) -> int:
    """Insere/atualiza as linhas em model_pricing (source='openrouter')."""
    for row in rows:
        session.execute(
            text(
                """
                INSERT INTO model_pricing
                    (model, input_usd_per_1m, output_usd_per_1m, currency, source, updated_at)
                VALUES
                    (:model, :input_usd_per_1m, :output_usd_per_1m, 'USD', 'openrouter', CURRENT_TIMESTAMP)
                ON CONFLICT (model) DO UPDATE SET
                    input_usd_per_1m = EXCLUDED.input_usd_per_1m,
                    output_usd_per_1m = EXCLUDED.output_usd_per_1m,
                    source = 'openrouter',
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            row,
        )
    session.commit()
    return len(rows)


def main() -> None:
    import requests

    from api.db.engine import SessionLocal

    response = requests.get(OPENROUTER_MODELS_URL, timeout=15)
    response.raise_for_status()
    rows = parse_openrouter_models(response.json())

    session = SessionLocal()
    try:
        count = upsert_pricing(session, rows)
        print(f"model_pricing sincronizado: {count} modelos.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
