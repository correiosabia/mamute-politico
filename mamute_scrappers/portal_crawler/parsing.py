"""Conversao dos campos textuais devolvidos pelo Portal da Transparencia.

Todos os valores monetarios chegam como string em formato brasileiro
("1.000.000,00") e o tipo de emenda chega como texto livre, sem enumeracao
declarada no OpenAPI da fonte.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

_NON_NUMERIC = re.compile(r"[^0-9,.\-]")

INDIVIDUAL_MARKER = "individual"


def normalize_text(value: Optional[str]) -> str:
    """Minusculas, sem diacriticos, espacos colapsados."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.lower().split())


def parse_brl(value: Any) -> Optional[Decimal]:
    """Converte "1.000.000,00" em Decimal("1000000.00").

    O ponto e sempre separador de milhar e a virgula sempre separador decimal,
    porque e o formato que a fonte usa. Devolve None quando o valor e vazio ou
    nao representa um numero.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    cleaned = _NON_NUMERIC.sub("", str(value).strip())
    if not cleaned or cleaned in {"-", ",", "."}:
        return None

    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def is_individual_amendment(amendment_type: Optional[str]) -> bool:
    """Verdadeiro para emendas de autoria individual.

    O OpenAPI da fonte declara `tipoEmenda` como string livre, sem enumerar os
    valores possiveis. Os dois valores observados na API real em 2026-08-06 sao
    "Emenda Individual - Transferencias com Finalidade Definida" e "Emenda de
    Bancada"; a checagem por substring normalizada acerta ambos e sobrevive a
    variacoes de caixa, acento e sufixo.
    """
    return INDIVIDUAL_MARKER in normalize_text(amendment_type)
