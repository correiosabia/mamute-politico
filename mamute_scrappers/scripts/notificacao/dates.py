"""Datas legislativas extraídas da proposição (alinhado à API/UI)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional


def extract_vote_date_from_proposition(
    details: Any,
    presentation_date: Optional[date],
) -> Optional[date]:
    """
    Data da votação a partir da proposição.

    1. `proposition.details.decisao_destino.Decisao.Data` (Senado — igual à API)
    2. `proposition.presentation_date` (fallback)
    """
    if isinstance(details, dict):
        decisao_destino = details.get("decisao_destino")
        if isinstance(decisao_destino, dict):
            decisao = decisao_destino.get("Decisao")
            if isinstance(decisao, dict):
                raw_date = decisao.get("Data")
                if isinstance(raw_date, str) and raw_date.strip():
                    try:
                        return date.fromisoformat(raw_date.strip()[:10])
                    except ValueError:
                        pass
                if isinstance(raw_date, date):
                    return raw_date
                if isinstance(raw_date, datetime):
                    return raw_date.date()

    return presentation_date


def format_activity_date(value: Optional[date | datetime]) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime("%d/%m/%Y")
