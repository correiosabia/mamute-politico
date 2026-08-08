"""Casamento entre candidatura do TSE e a base de parlamentares.

CPF primeiro: e identificador civil, imune a homonimo (100% dos deputados tem
CPF na base; medido em producao em 2026-08-07). Senadores nao tem CPF na base,
entao caem na cascata por nome normalizado — exata, sem fuzzy, pela mesma
razao do author_matching das emendas: em produto de transparencia, palpite
silencioso e pior que lacuna declarada.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional, Sequence

from .parsing import normalize_cpf, normalize_text

MATCH_STATUS_CPF = "matched_cpf"
MATCH_STATUS_NAME = "matched_name"
MATCH_STATUS_AMBIGUOUS = "ambiguous"
MATCH_STATUS_UNMATCHED = "unmatched"
MATCH_STATUS_MANUAL = "manual"


class ParliamentarianRecord(NamedTuple):
    id: int
    name: Optional[str]
    full_name: Optional[str]
    cpf: Optional[str]
    state_elected: Optional[str]


class MatchResult(NamedTuple):
    parliamentarian_id: Optional[int]
    status: str


class MatchIndex(NamedTuple):
    by_cpf: Dict[str, List[ParliamentarianRecord]]
    by_name: Dict[str, List[ParliamentarianRecord]]


def build_index(records: Sequence[ParliamentarianRecord]) -> MatchIndex:
    by_cpf: Dict[str, List[ParliamentarianRecord]] = {}
    by_name: Dict[str, List[ParliamentarianRecord]] = {}
    for record in records:
        cpf = normalize_cpf(record.cpf)
        if cpf:
            by_cpf.setdefault(cpf, []).append(record)
        for attribute in (record.full_name, record.name):
            key = normalize_text(attribute)
            if key:
                bucket = by_name.setdefault(key, [])
                if record not in bucket:
                    bucket.append(record)
    return MatchIndex(by_cpf=by_cpf, by_name=by_name)


def _resolve_by_state(
    hits: List[ParliamentarianRecord], state: Optional[str]
) -> MatchResult:
    if len(hits) == 1:
        return MatchResult(hits[0].id, MATCH_STATUS_NAME)
    state_key = normalize_text(state)
    filtered = [
        hit for hit in hits if normalize_text(hit.state_elected) == state_key
    ]
    if len(filtered) == 1:
        return MatchResult(filtered[0].id, MATCH_STATUS_NAME)
    return MatchResult(None, MATCH_STATUS_AMBIGUOUS)


def match_candidacy(
    *,
    cpf: Optional[str],
    full_name: Optional[str],
    ballot_name: Optional[str],
    state: Optional[str],
    index: MatchIndex,
) -> MatchResult:
    cpf_key = normalize_cpf(cpf)
    if cpf_key:
        hits = index.by_cpf.get(cpf_key, [])
        if len(hits) == 1:
            return MatchResult(hits[0].id, MATCH_STATUS_CPF)
        if len(hits) > 1:
            return MatchResult(None, MATCH_STATUS_AMBIGUOUS)

    for name in (full_name, ballot_name):
        key = normalize_text(name)
        if not key:
            continue
        hits = index.by_name.get(key, [])
        if hits:
            return _resolve_by_state(hits, state)

    return MatchResult(None, MATCH_STATUS_UNMATCHED)


__all__ = [
    "MATCH_STATUS_AMBIGUOUS",
    "MATCH_STATUS_CPF",
    "MATCH_STATUS_MANUAL",
    "MATCH_STATUS_NAME",
    "MATCH_STATUS_UNMATCHED",
    "MatchIndex",
    "MatchResult",
    "ParliamentarianRecord",
    "build_index",
    "match_candidacy",
]
