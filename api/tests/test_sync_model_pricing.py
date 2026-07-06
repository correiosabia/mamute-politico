"""Parser do payload do OpenRouter → linhas de model_pricing."""
from __future__ import annotations

from scripts.sync_model_pricing import parse_openrouter_models

PAYLOAD = {
    "data": [
        {
            "id": "google/gemini-2.5-flash",
            "pricing": {"prompt": "0.0000003", "completion": "0.0000025"},
        },
        {
            "id": "sem-preco",
            "pricing": {"prompt": None, "completion": "0.00001"},
        },
        {"id": "sem-pricing"},
    ]
}


def test_parse_converts_per_token_to_per_million() -> None:
    rows = parse_openrouter_models(PAYLOAD)
    assert len(rows) == 1
    row = rows[0]
    assert row["model"] == "google/gemini-2.5-flash"
    assert row["input_usd_per_1m"] == 0.30
    assert row["output_usd_per_1m"] == 2.50


def test_parse_empty() -> None:
    assert parse_openrouter_models({}) == []
