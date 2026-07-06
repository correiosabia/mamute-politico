"""DB (tier.detalhes) deve ganhar do env no limite de parlamentares."""
from __future__ import annotations

import pytest

from api.routers import projects


class _FakeTier:
    def __init__(self, detalhes: dict) -> None:
        self.detalhes = detalhes
        self.product_id = "cidadao-mamute"


class _FakeProject:
    def __init__(self, detalhes: dict, qtd_termos_col: int = 0) -> None:
        self.tier = _FakeTier(detalhes)
        self.cliente = "cidadao-mamute"
        self.qtd_termos = qtd_termos_col


def test_db_detalhes_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # env diz 3; DB diz 7 → deve valer 7.
    monkeypatch.setenv(
        "MAMUTE_TIER_LIMITS_JSON",
        '{"cidadao-mamute": {"qtd_termos": 3}}',
    )
    project = _FakeProject({"qtd_termos": 7})
    assert projects._project_favorite_limit(project) == 7


def test_env_used_when_db_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MAMUTE_TIER_LIMITS_JSON",
        '{"cidadao-mamute": {"qtd_termos": 3}}',
    )
    project = _FakeProject({})  # sem qtd_termos no DB
    assert projects._project_favorite_limit(project) == 3


def test_column_fallback_when_both_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAMUTE_TIER_LIMITS_JSON", raising=False)
    project = _FakeProject({}, qtd_termos_col=2)
    assert projects._project_favorite_limit(project) == 2
