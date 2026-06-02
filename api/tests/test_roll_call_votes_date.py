"""Testes de resolução de date_vote no endpoint roll-call-votes."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from api.routers.roll_call_votes import (
    _extract_date_vote_legacy,
    _resolve_date_vote,
)


def _make_vote(*, vote_date=None, proposition_details=None):
    """Constrói um stub mínimo de RollCallVote para os helpers que só acessam
    `vote.vote_date` e `vote.proposition.details`."""
    proposition = (
        SimpleNamespace(details=proposition_details)
        if proposition_details is not None
        else None
    )
    return SimpleNamespace(vote_date=vote_date, proposition=proposition)


def test_resolve_uses_column_when_populated() -> None:
    vote = _make_vote(
        vote_date=date(2024, 8, 14),
        proposition_details={
            "decisao_destino": {"Decisao": {"Data": "2020-01-01"}}
        },
    )
    # Coluna preenchida vence o fallback do JSON, mesmo se o JSON também existir.
    assert _resolve_date_vote(vote) == date(2024, 8, 14)


def test_resolve_falls_back_to_legacy_json_when_column_null() -> None:
    vote = _make_vote(
        vote_date=None,
        proposition_details={
            "decisao_destino": {"Decisao": {"Data": "2024-08-14"}}
        },
    )
    assert _resolve_date_vote(vote) == date(2024, 8, 14)


def test_resolve_returns_none_when_neither_source_has_date() -> None:
    vote = _make_vote(vote_date=None, proposition_details={})
    assert _resolve_date_vote(vote) is None


def test_resolve_returns_none_when_proposition_missing() -> None:
    vote = _make_vote(vote_date=None, proposition_details=None)
    assert _resolve_date_vote(vote) is None


def test_legacy_extractor_returns_none_when_data_malformed() -> None:
    details = {"decisao_destino": {"Decisao": {"Data": "not-a-date"}}}
    proposition = SimpleNamespace(details=details)
    assert _extract_date_vote_legacy(proposition) is None


def test_legacy_extractor_returns_none_when_decision_missing() -> None:
    details = {"unrelated_key": True}
    proposition = SimpleNamespace(details=details)
    assert _extract_date_vote_legacy(proposition) is None


def test_legacy_extractor_handles_non_dict_details() -> None:
    proposition = SimpleNamespace(details="not a dict")
    assert _extract_date_vote_legacy(proposition) is None
