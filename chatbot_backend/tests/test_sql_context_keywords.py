"""Extração de palavras-chave do SQL context: stoplists e nomes filtrados.

O caso real que motivou isto: "O que diz o(a) parlamentar Jaques Wagner sobre
Greve" virava keywords ['greve','jaques','parlamentar','wagner'] — e
ILIKE '%parlamentar%' casa com praticamente todos os discursos (seq scan de
~15s por consulta e contexto poluído). O tema é a única keyword que importa.
"""
from __future__ import annotations

import pytest

from chatbot_backend.app.services import sql_context


@pytest.fixture(autouse=True)
def _reset_dynamic_cache(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sql_context, "_dynamic_stopwords_cache", None)
    yield


def test_template_da_nuvem_reduz_ao_tema() -> None:
    keywords = sql_context._extract_keywords(
        "O que diz o(a) parlamentar Jaques Wagner sobre Greve",
        extra_stopwords={"jaques", "wagner"},
    )
    assert keywords == ["greve"]


def test_pergunta_generica_mantem_termos_uteis() -> None:
    keywords = sql_context._extract_keywords(
        "Quero saber discursos de parlamentares que falaram sobre greve. Qualquer parlamentar."
    )
    assert keywords == ["greve"]


def test_stopwords_dinamicas_vem_de_word_cloud_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_execute(query: str, params: dict) -> list[dict]:
        calls.append(query)
        return [{"term": "V. Exa."}, {"term": "mudança climática"}, {"term": "bloco"}]

    monkeypatch.setattr(sql_context, "_execute_query", fake_execute)

    words = sql_context._load_dynamic_stopwords()
    assert {"exa", "mudança", "climática", "bloco"} <= set(words)

    # Segunda chamada usa o cache (TTL): não consulta o banco de novo.
    sql_context._load_dynamic_stopwords()
    assert len(calls) == 1


def test_stopwords_dinamicas_fail_soft(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(query: str, params: dict) -> list[dict]:
        raise RuntimeError("db off")

    monkeypatch.setattr(sql_context, "_execute_query", boom)
    assert sql_context._load_dynamic_stopwords() == frozenset()


def test_nomes_de_parlamentares_filtrados_viram_stopwords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute(query: str, params: dict) -> list[dict]:
        assert params == {"ids": [553]}
        return [{"name": "Jaques Wagner"}]

    monkeypatch.setattr(sql_context, "_execute_query", fake_execute)

    tokens = sql_context._filtered_parliamentarian_name_tokens(
        {"parliamentarian_ids": [553]}
    )
    assert tokens == {"jaques", "wagner"}


def test_sem_filtro_nao_consulta_nomes(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(query: str, params: dict) -> list[dict]:
        raise AssertionError("não deveria consultar o banco")

    monkeypatch.setattr(sql_context, "_execute_query", boom)
    assert sql_context._filtered_parliamentarian_name_tokens(None) == set()
    assert sql_context._filtered_parliamentarian_name_tokens({}) == set()
