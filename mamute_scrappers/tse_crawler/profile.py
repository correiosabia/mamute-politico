"""Perfil demografico dos candidatos (CS-63).

Normaliza os campos de perfil das duas fontes para a MESMA forma — a dos CSVs
de dados abertos do TSE, em maiusculas — para que agregacoes cruzem eleicoes
sem GROUP BY quebrado: a DivulgaCandContas devolve "MASC."/"Superior
completo", o CSV devolve "MASCULINO"/"SUPERIOR COMPLETO".

Sentinelas dos CSVs (#NE, #NE#, #NULO, #NULO#) viram None: ausencia real da
fonte (cor/raca so existe desde 2014; federacao desde 2022).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional

from mamute_scrappers.tse_crawler.parsing import coerce_text

PROFILE_SOURCE_API = "divulgacand"
PROFILE_SOURCE_CSV = "tse_csv"

# Abreviacoes da DivulgaCandContas -> forma dos CSVs.
_GENDER_MAP = {
    "MASC.": "MASCULINO",
    "FEM.": "FEMININO",
}

PROFILE_FIELDS = (
    "birth_date",
    "gender",
    "race",
    "education",
    "occupation",
    "marital_status",
    "nationality",
    "federation",
)


def normalize_profile_text(value: Any) -> Optional[str]:
    """Texto de perfil em maiusculas; sentinelas do TSE viram None."""
    text = coerce_text(value)
    if text is None or text.startswith("#"):
        return None
    return text.upper()


def parse_birth_date(value: Any) -> Optional[date]:
    """Converte "1970-10-20" (API) ou "05/02/1956" (CSV)."""
    text = coerce_text(value)
    if not text or text.startswith("#"):
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _normalize_gender(value: Any) -> Optional[str]:
    text = normalize_profile_text(value)
    return _GENDER_MAP.get(text, text) if text else None


def extract_profile_from_detail(detail: Dict[str, Any]) -> Dict[str, Any]:
    """Campos de perfil do payload de detalhe da DivulgaCandContas.

    A API nao expoe federacao (conferido ao vivo em 2026-08-20): fica None e
    pode ser completada pelo CSV (regra fill-NULL do loader).
    """
    return {
        "birth_date": parse_birth_date(detail.get("dataDeNascimento")),
        "gender": _normalize_gender(detail.get("descricaoSexo")),
        "race": normalize_profile_text(detail.get("descricaoCorRaca")),
        "education": normalize_profile_text(detail.get("grauInstrucao")),
        "occupation": normalize_profile_text(detail.get("ocupacao")),
        "marital_status": normalize_profile_text(detail.get("descricaoEstadoCivil")),
        "nationality": normalize_profile_text(detail.get("nacionalidade")),
        "federation": None,
        "profile_source": PROFILE_SOURCE_API,
    }


def extract_profile_from_csv_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Campos de perfil de uma linha do consulta_cand (dados abertos)."""
    return {
        "birth_date": parse_birth_date(row.get("DT_NASCIMENTO")),
        "gender": _normalize_gender(row.get("DS_GENERO")),
        "race": normalize_profile_text(row.get("DS_COR_RACA")),
        "education": normalize_profile_text(row.get("DS_GRAU_INSTRUCAO")),
        "occupation": normalize_profile_text(row.get("DS_OCUPACAO")),
        "marital_status": normalize_profile_text(row.get("DS_ESTADO_CIVIL")),
        "nationality": normalize_profile_text(row.get("DS_NACIONALIDADE")),
        "federation": normalize_profile_text(row.get("SG_FEDERACAO")),
        "profile_source": PROFILE_SOURCE_CSV,
    }


__all__ = [
    "PROFILE_FIELDS",
    "PROFILE_SOURCE_API",
    "PROFILE_SOURCE_CSV",
    "extract_profile_from_csv_row",
    "extract_profile_from_detail",
    "normalize_profile_text",
    "parse_birth_date",
]
