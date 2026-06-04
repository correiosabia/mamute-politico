"""Testa que o crawler de proposições da Câmara filtra pela data de APRESENTAÇÃO.

Antes, o crawler usava `dataInicio`/`dataFim` (data de tramitação), o que fazia
janelas semanais capturarem ~3.800 itens espalhados por vários anos em vez das
~720 efetivamente apresentadas no intervalo. O fix migra para
`ano` + `dataApresentacaoInicio`/`dataApresentacaoFim`."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


crawler = _load(
    "test_camara_proposition_params",
    "mamute_scrappers/camara_crawler/proposition.py",
)


def _drain_one_call(monkeypatch) -> dict:
    """Captura os params da primeira chamada a `_request_json` feita pelo iterator."""
    captured: dict = {}

    def fake_request(url, *, params=None):
        captured["url"] = url
        captured["params"] = dict(params or {})
        # Resposta vazia interrompe a paginação imediatamente.
        return {"dados": [], "links": []}

    monkeypatch.setattr(crawler, "_request_json", fake_request)
    return captured


def test_uses_data_apresentacao_when_data_inicio_and_data_fim_passed(monkeypatch) -> None:
    captured = _drain_one_call(monkeypatch)

    # Consome o iterator (vazio); só queremos a primeira chamada à API.
    list(
        crawler._iter_propositions_paginated(
            year_start=2024,
            data_inicio="2024-06-03",
            data_fim="2024-06-09",
        )
    )

    params = captured["params"]
    assert params["ano"] == 2024
    assert params["dataApresentacaoInicio"] == "2024-06-03"
    assert params["dataApresentacaoFim"] == "2024-06-09"
    # Sem regressão: parâmetros legados não voltam acidentalmente.
    assert "dataInicio" not in params
    assert "dataFim" not in params


def test_omits_data_fim_when_open_ended(monkeypatch) -> None:
    captured = _drain_one_call(monkeypatch)

    list(
        crawler._iter_propositions_paginated(
            year_start=2024,
            data_inicio="2024-06-03",
        )
    )

    params = captured["params"]
    assert params["dataApresentacaoInicio"] == "2024-06-03"
    assert "dataApresentacaoFim" not in params
    assert params["ano"] == 2024


def test_defaults_to_year_start_first_day_when_no_data_inicio(monkeypatch) -> None:
    captured = _drain_one_call(monkeypatch)

    # session=None desabilita busca incremental; sem data_inicio -> 1º de janeiro.
    list(crawler._iter_propositions_paginated(year_start=2023, session=None))

    params = captured["params"]
    assert params["dataApresentacaoInicio"] == "2023-01-01"
    assert params["ano"] == 2023


def test_dead_code_fetch_propositions_list_removed() -> None:
    # Regressão estrutural: a helper antiga não-utilizada não deve voltar.
    assert not hasattr(crawler, "_fetch_propositions_list")
