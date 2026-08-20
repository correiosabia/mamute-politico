"""Conversao dos payloads da DivulgaCandContas.

O fingerprint cobre apenas os campos da LISTAGEM que disparam refetch do
detalhe. Campos volateis ou que so existem no detalhe ficam de fora de
proposito: mudanca neles nao deve custar 29 mil requests.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

from mamute_scrappers.portal_crawler.parsing import normalize_text

_DIGITS_ONLY = re.compile(r"\D")

# Campos da listagem observados na API real em 2026-08-07. `descricaoSituacao`
# e o que mais muda (Aguardando julgamento -> Deferido/Indeferido).
_FINGERPRINT_FIELDS = (
    "nomeUrna",
    "numero",
    "nomeCompleto",
    "descricaoSituacao",
    "descricaoTotalizacao",
    "nomeColigacao",
)


def coerce_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def parse_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def normalize_cpf(value: Any) -> Optional[str]:
    """Digitos do CPF, ou None quando nao ha exatamente 11."""
    if value is None:
        return None
    digits = _DIGITS_ONLY.sub("", str(value))
    return digits if len(digits) == 11 else None


def parse_tse_datetime(value: Any) -> Optional[datetime]:
    """Converte "2026-08-05 11:25" (formato observado no detalhe)."""
    text = coerce_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _party_sigla(item: Dict[str, Any]) -> Optional[str]:
    party = item.get("partido")
    if isinstance(party, dict):
        return coerce_text(party.get("sigla"))
    return None


def compute_listing_fingerprint(item: Dict[str, Any]) -> str:
    material = [coerce_text(item.get(field)) for field in _FINGERPRINT_FIELDS]
    material.append(_party_sigla(item))
    blob = json.dumps(material, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_listing_payload(
    item: Dict[str, Any],
    *,
    election_year: int,
    office_code: int,
    office_name: str,
    state: str,
) -> Optional[Dict[str, Any]]:
    tse_candidate_id = parse_int(item.get("id"))
    if tse_candidate_id is None:
        return None

    return {
        "election_year": election_year,
        "tse_candidate_id": tse_candidate_id,
        "office_code": office_code,
        "office": office_name,
        "state": state,
        "ballot_number": parse_int(item.get("numero")),
        "ballot_name": coerce_text(item.get("nomeUrna")),
        "full_name": coerce_text(item.get("nomeCompleto")),
        "party": _party_sigla(item),
        "coalition": coerce_text(item.get("nomeColigacao")),
        "status": coerce_text(item.get("descricaoSituacao")),
        "totalization_status": coerce_text(item.get("descricaoTotalizacao")),
    }


def merge_detail_payload(
    payload: Dict[str, Any], detail: Dict[str, Any]
) -> Dict[str, Any]:
    # Import tardio: profile.py importa deste modulo (coerce_text).
    from mamute_scrappers.tse_crawler.profile import extract_profile_from_detail

    merged = dict(payload)
    merged["cpf"] = normalize_cpf(detail.get("cpf"))
    merged["voter_id"] = coerce_text(detail.get("tituloEleitor"))
    merged["photo_url"] = coerce_text(detail.get("fotoUrl"))
    merged["tse_last_update"] = parse_tse_datetime(detail.get("dataUltimaAtualizacao"))
    merged["details"] = detail
    merged.update(extract_profile_from_detail(detail))
    return merged


__all__ = [
    "build_listing_payload",
    "coerce_text",
    "compute_listing_fingerprint",
    "merge_detail_payload",
    "normalize_cpf",
    "normalize_text",
    "parse_int",
    "parse_tse_datetime",
]
