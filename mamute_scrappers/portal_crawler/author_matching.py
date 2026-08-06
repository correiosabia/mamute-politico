"""Casamento entre o autor textual da emenda e a base de parlamentares.

O Portal da Transparencia nao devolve identificador de parlamentar: o autor vem
apenas como texto em `nomeAutor`. Este modulo resolve esse texto para um id da
tabela `parliamentarian`, ou declara explicitamente que nao conseguiu.

Nao existe casamento aproximado aqui, e isso e deliberado. Fuzzy silencioso em
produto de transparencia atribui dinheiro publico a pessoa errada, e o erro e
invisivel justamente por ser silencioso. Sugestao aproximada, se um dia
existir, e trabalho do painel de administracao, revisada por humano.

Medicao contra a API real em 2026-08-06: 94% de casamento e zero ambiguos,
contra 593 parlamentares em exercicio. A fonte publica o nome parlamentar em
caixa alta ("HEITOR SCHUCH"), nao o nome civil.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional, Sequence

from .parsing import normalize_text

MATCH_STATUS_MATCHED = "matched"
MATCH_STATUS_UNMATCHED = "unmatched"
MATCH_STATUS_AMBIGUOUS = "ambiguous"
MATCH_STATUS_MANUAL = "manual"


class ParliamentarianCandidate(NamedTuple):
    """Parlamentar candidato, desacoplado do modelo SQLAlchemy."""

    id: int
    name: Optional[str]
    full_name: Optional[str]


class MatchResult(NamedTuple):
    parliamentarian_id: Optional[int]
    status: str


def _index_by(
    candidates: Sequence[ParliamentarianCandidate],
    attribute: str,
) -> Dict[str, List[int]]:
    index: Dict[str, List[int]] = {}
    for candidate in candidates:
        key = normalize_text(getattr(candidate, attribute))
        if not key:
            continue
        index.setdefault(key, []).append(candidate.id)
    return index


def _resolve(ids: List[int]) -> Optional[MatchResult]:
    if len(ids) == 1:
        return MatchResult(ids[0], MATCH_STATUS_MATCHED)
    if len(ids) > 1:
        return MatchResult(None, MATCH_STATUS_AMBIGUOUS)
    return None


def match_author(
    author_name: Optional[str],
    candidates: Sequence[ParliamentarianCandidate],
) -> MatchResult:
    """Resolve o nome textual do autor para um parlamentar.

    A cascata tenta primeiro o nome parlamentar (`name`) e so depois o nome
    civil (`full_name`). Um nome que case com mais de um parlamentar devolve
    `ambiguous` sem escolher nenhum.
    """
    key = normalize_text(author_name)
    if not key or not candidates:
        return MatchResult(None, MATCH_STATUS_UNMATCHED)

    for attribute in ("name", "full_name"):
        resolved = _resolve(_index_by(candidates, attribute).get(key, []))
        if resolved is not None:
            return resolved

    return MatchResult(None, MATCH_STATUS_UNMATCHED)


__all__ = [
    "MATCH_STATUS_AMBIGUOUS",
    "MATCH_STATUS_MANUAL",
    "MATCH_STATUS_MATCHED",
    "MATCH_STATUS_UNMATCHED",
    "MatchResult",
    "ParliamentarianCandidate",
    "match_author",
]
