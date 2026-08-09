"""Conversao do historico eleitoral (`eleicoesAnteriores`) e dos bens.

`eleicoesAnteriores` vem no detalhe de cada candidatura da DivulgaCandContas
com ids em string e inclui a propria eleicao corrente. Entrada sem id ou sem
ano nao tem como virar linha de timeline — o chamador descarta com log,
nunca com excecao.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from .parsing import coerce_text, parse_int


def _parse_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def build_history_payload(
    entry: Dict[str, Any],
    *,
    candidacy_id: Optional[int] = None,
    parliamentarian_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    tse_candidate_id = parse_int(entry.get("id"))
    election_year = parse_int(entry.get("nrAno"))
    if tse_candidate_id is None or election_year is None:
        return None

    return {
        "election_year": election_year,
        "tse_candidate_id": tse_candidate_id,
        "tse_election_id": parse_int(entry.get("idEleicao")),
        "office": coerce_text(entry.get("cargo")),
        "state": coerce_text(entry.get("sgUe")),
        "locality": coerce_text(entry.get("local")),
        "party": coerce_text(entry.get("partido")),
        "ballot_name": coerce_text(entry.get("nomeUrna")),
        "full_name": coerce_text(entry.get("nomeCandidato")),
        "ballot_number": parse_int(entry.get("nrCandidato")),
        "result": coerce_text(entry.get("situacaoTotalizacao")),
        "source_link": coerce_text(entry.get("txLink")),
        "candidacy_id": candidacy_id,
        "parliamentarian_id": parliamentarian_id,
    }


def build_assets_payload(detail: Dict[str, Any]) -> Dict[str, Any]:
    """Extrai patrimonio de um payload de detalhe (ou do `details` da 2026).

    `totalDeBens` e a fonte da verdade; na ausencia dele, soma dos itens.
    """
    bens = detail.get("bens")
    items: List[Dict[str, Any]] = bens if isinstance(bens, list) else []

    total = _parse_decimal(detail.get("totalDeBens"))
    if total is None and items:
        parcels = [_parse_decimal(item.get("valor")) for item in items]
        valid = [p for p in parcels if p is not None]
        total = sum(valid, Decimal("0.00")) if valid else None

    return {"declared_assets": total, "assets_count": len(items), "assets": items}


__all__ = ["build_assets_payload", "build_history_payload"]
