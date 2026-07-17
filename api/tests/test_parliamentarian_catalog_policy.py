"""Testes da política de visibilidade do catálogo de parlamentares."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api import main
from api.routers.parliamentarians import (
    ParliamentarianSituation,
    _resolve_catalog_situacao,
    get_parliamentarian_catalog_config,
    get_parliamentarian_catalog_scope,
)


def test_catalog_scope_defaults_to_current_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAMUTE_PARLIAMENTARIAN_CATALOG_SCOPE", raising=False)

    assert get_parliamentarian_catalog_scope().value == "current_only"
    config = get_parliamentarian_catalog_config()
    assert config.allowed_situations == [ParliamentarianSituation.EXERCICIO]
    assert config.default_situacao is ParliamentarianSituation.EXERCICIO


def test_catalog_scope_invalid_value_falls_back_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAMUTE_PARLIAMENTARIAN_CATALOG_SCOPE", "unexpected")

    assert get_parliamentarian_catalog_scope().value == "current_only"


def test_boulos_like_licensed_record_is_restricted_in_current_only() -> None:
    config = get_parliamentarian_catalog_config("current_only")

    with pytest.raises(HTTPException) as exc_info:
        _resolve_catalog_situacao(ParliamentarianSituation.LICENCIADO, config=config)

    assert exc_info.value.status_code == 403


def test_boulos_like_licensed_record_is_allowed_when_scope_includes_licensed() -> None:
    config = get_parliamentarian_catalog_config("current_and_licensed")

    assert _resolve_catalog_situacao(
        ParliamentarianSituation.LICENCIADO,
        config=config,
    ) is ParliamentarianSituation.LICENCIADO


def test_all_ingested_scope_exposes_every_supported_situation() -> None:
    config = get_parliamentarian_catalog_config("all_ingested")

    assert config.allowed_situations == list(ParliamentarianSituation)
    for situacao in ParliamentarianSituation:
        assert _resolve_catalog_situacao(situacao, config=config) is situacao


def test_authenticated_catalog_config_endpoint_returns_runtime_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAMUTE_PARLIAMENTARIAN_CATALOG_SCOPE", "current_and_licensed")
    main.app.dependency_overrides[main.verify_token] = lambda: {"sub": "member@example.com"}
    try:
        response = TestClient(main.app).get("/api/parliamentarians/catalog-config")
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "allowed_situations": ["exercicio", "licenciado"],
        "default_situacao": "exercicio",
    }
