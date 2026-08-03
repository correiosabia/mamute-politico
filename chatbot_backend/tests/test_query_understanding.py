"""Interpretação da pergunta pelo LLM: parsing, fallback e integração.

Motivação (caso real): a heurística de keywords promoveu "geral" a termo de
busca em "o que parlamentares falaram sobre a APAE, no geral?". A correção de
verdade é interpretar o CONTEXTO da pergunta — a stoplist fica só de fallback.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from chatbot_backend.app.services import chat_service, sql_context
from chatbot_backend.app.services.query_understanding import _parse_intent


def test_parse_intent_json_valido() -> None:
    parsed = _parse_intent('{"temas": ["APAE", "educação especial"], "panoramica": true}')
    assert parsed == {"temas": ["APAE", "educação especial"], "panoramica": True}


def test_parse_intent_json_embutido_em_texto() -> None:
    raw = 'Aqui está: {"temas": ["reforma tributária"], "panoramica": false} :)'
    parsed = _parse_intent(raw)
    assert parsed == {"temas": ["reforma tributária"], "panoramica": False}


def test_parse_intent_limita_e_deduplica_temas() -> None:
    parsed = _parse_intent(
        '{"temas": ["APAE", "apae", "saúde", "esporte", "futebol"], "panoramica": true}'
    )
    assert parsed is not None
    assert parsed["temas"] == ["APAE", "saúde", "esporte"]


@pytest.mark.parametrize(
    "raw",
    ["", "não sei", '{"panoramica": true}', '{"temas": []}', '{"temas": "apae"}'],
)
def test_parse_intent_invalido_vira_none(raw: str) -> None:
    assert _parse_intent(raw) is None


def _service_with_intent(monkeypatch: pytest.MonkeyPatch, intent: Any) -> Any:
    service = chat_service.ChatbotService()

    async def fake_interpret(question: str, request_id: str = "n/a") -> Any:
        return intent

    monkeypatch.setattr(service.query_understanding, "ainterpret", fake_interpret)
    return service


def test_enrich_anexa_temas_interpretados(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_intent(
        monkeypatch, {"temas": ["APAE"], "panoramica": True}
    )
    enriched = asyncio.run(
        service._enrich_inputs({"question": "o que falaram sobre a APAE, no geral?"})
    )
    assert enriched["derived_topics"] == ["APAE"]


def test_enrich_fail_soft_sem_interpretacao(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_intent(monkeypatch, None)
    inputs = {"question": "qualquer coisa"}
    assert asyncio.run(service._enrich_inputs(inputs)) == inputs


def test_enrich_nao_interpreta_com_tema_explicito(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = chat_service.ChatbotService()

    async def boom(question: str, request_id: str = "n/a") -> Any:
        raise AssertionError("tema explícito da nuvem não deve ser reinterpretado")

    monkeypatch.setattr(service.query_understanding, "ainterpret", boom)
    inputs = {"question": "O que diz o(a) parlamentar Romário sobre Apae", "topic": "apae"}
    assert asyncio.run(service._enrich_inputs(inputs)) == inputs


def test_sql_context_usa_temas_interpretados_como_frases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[dict] = []

    def fake_soft(query: str, params: dict, *, section: str, request_id: str) -> list:
        recorded.append(params)
        return []

    def boom(query: str, params: dict) -> list:
        raise AssertionError("com temas interpretados não deve usar a heurística")

    monkeypatch.setattr(sql_context, "_execute_query_soft", fake_soft)
    monkeypatch.setattr(sql_context, "_execute_query", boom)

    sql_context.fetch_sql_context(
        "o que falaram sobre a reforma tributária, no geral?",
        None,
        request_id="t-derived",
        derived_topics=["reforma tributária"],
    )
    patterns = [p.get("pattern_0") for p in recorded if "pattern_0" in p]
    assert patterns and all(p == "%reforma tributária%" for p in patterns)
    assert all("geral" not in str(p) for p in recorded)
