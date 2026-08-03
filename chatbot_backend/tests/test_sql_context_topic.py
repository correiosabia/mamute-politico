"""Tema estruturado (clique na nuvem) ancora o SQL context.

Sem o tema estruturado, "O que diz o(a) parlamentar X sobre Greve" dependia da
extração de keywords da pergunta — e a nuvem prometia um tema que a busca não
priorizava. Com `topic`, o termo vira condição obrigatória (frase inteira).
"""
from __future__ import annotations

import pytest

from chatbot_backend.app.services import sql_context


def test_topic_vira_condicao_obrigatoria(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[tuple[str, str, dict]] = []

    def fake_soft(query: str, params: dict, *, section: str, request_id: str) -> list:
        recorded.append((section, query, params))
        return []

    def boom(query: str, params: dict) -> list:
        raise AssertionError(
            "com topic não deve carregar stoplist dinâmica nem nomes"
        )

    monkeypatch.setattr(sql_context, "_execute_query_soft", fake_soft)
    monkeypatch.setattr(sql_context, "_execute_query", boom)

    out = sql_context.fetch_sql_context(
        "O que diz o(a) parlamentar Jaques Wagner sobre Greve",
        {"parliamentarian_ids": [553]},
        request_id="t-topic",
        topic="Greve",
    )
    assert out == ""

    sections = {section for section, _, _ in recorded}
    assert "context" in sections

    for section, query, params in recorded:
        if section == "context_fallback":
            # Fallback é deliberadamente sem keywords: últimos discursos do
            # parlamentar quando nada casa com o tema.
            assert "topic_pattern" not in params
            continue
        assert params.get("topic_pattern") == "%Greve%"
        assert ":topic_pattern" in query
        # O filtro por parlamentar continua valendo junto com o tema.
        assert params.get("filter_parliamentarian_ids") == [553]


def test_sem_topic_mantem_extracao_de_keywords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[dict] = []

    def fake_soft(query: str, params: dict, *, section: str, request_id: str) -> list:
        recorded.append(params)
        return []

    monkeypatch.setattr(sql_context, "_execute_query_soft", fake_soft)
    monkeypatch.setattr(sql_context, "_load_dynamic_stopwords", lambda: frozenset())
    monkeypatch.setattr(
        sql_context, "_filtered_parliamentarian_name_tokens", lambda filters: set()
    )

    sql_context.fetch_sql_context(
        "Quem falou sobre greve?", None, request_id="t-plain"
    )
    assert any("pattern_0" in params for params in recorded)
    assert all("topic_pattern" not in params for params in recorded)
