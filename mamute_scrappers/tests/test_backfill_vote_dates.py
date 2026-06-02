"""Testes das funções puras do orquestrador backfill_vote_dates."""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bvd = _load(
    "test_backfill_vote_dates_module",
    "mamute_scrappers/scripts/backfill_vote_dates.py",
)


def test_parse_date_iso_with_time() -> None:
    assert bvd._parse_date("2024-08-14T15:30:00") == date(2024, 8, 14)


def test_parse_date_iso_date_only() -> None:
    assert bvd._parse_date("2024-08-14") == date(2024, 8, 14)


def test_parse_date_brazilian_format() -> None:
    assert bvd._parse_date("14/08/2024") == date(2024, 8, 14)


def test_parse_date_returns_none_for_garbage() -> None:
    assert bvd._parse_date("not-a-date") is None
    assert bvd._parse_date("") is None
    assert bvd._parse_date(None) is None


def test_scan_for_date_finds_top_level_key() -> None:
    payload = {"DataSessao": "2024-08-14 14:30:00"}
    assert bvd._scan_for_date(payload, keys=("DataSessao",)) == date(2024, 8, 14)


def test_scan_for_date_finds_nested_key() -> None:
    payload = {
        "ListaVotacoes": {
            "Votacao": {"dataSessao": "2023-05-10"},
        }
    }
    assert bvd._scan_for_date(payload, keys=("DataSessao", "dataSessao")) == date(
        2023, 5, 10
    )


def test_scan_for_date_searches_lists() -> None:
    payload = {"items": [{"x": 1}, {"DataHoraInicio": "2024-01-15T09:00:00"}]}
    assert bvd._scan_for_date(payload, keys=("DataHoraInicio",)) == date(2024, 1, 15)


def test_scan_for_date_returns_none_when_absent() -> None:
    payload = {"OutroCampo": "irrelevante"}
    assert bvd._scan_for_date(payload, keys=("DataSessao",)) is None


def test_resolve_fetcher_dispatches_by_url_host() -> None:
    assert (
        bvd._resolve_fetcher("https://dadosabertos.camara.leg.br/api/v2/votacoes/123")
        is bvd._fetch_camara_date
    )
    assert (
        bvd._resolve_fetcher("https://legis.senado.leg.br/dadosabertos/votacao/45")
        is bvd._fetch_senado_date
    )
    assert bvd._resolve_fetcher("https://example.com/foo") is None
