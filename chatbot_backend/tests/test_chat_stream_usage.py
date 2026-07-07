"""Registro de uso no stream: uma resposta ENTREGUE conta como 'completed'
(com tokens) mesmo se o cliente desconectar no fim do stream — antes virava
'cancelled' sem tokens e sumia das métricas."""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

import pytest

from chatbot_backend.app.routers import chat
from chatbot_backend.app.schemas import ChatRequest

# token "ok" (2 chars) → usage (10/20) → end
_CHUNKS = [
    {"type": "token", "value": "ok"},
    {"type": "usage", "prompt_tokens": 10, "completion_tokens": 20},
    {"type": "end"},
]


class _StubService:
    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self._chunks = chunks

    async def stream_response(
        self, inputs: dict[str, Any], request_id: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        for c in self._chunks:
            yield c


def _patch(monkeypatch: pytest.MonkeyPatch, chunks: list[dict[str, Any]]) -> list[dict]:
    monkeypatch.setattr(chat, "service", _StubService(chunks))
    monkeypatch.setattr(chat, "_start_usage_or_raise", lambda *a, **k: 123)
    calls: list[dict] = []
    monkeypatch.setattr(
        chat, "_mark_usage", lambda usage_id, **kw: calls.append({"usage_id": usage_id, **kw})
    )
    return calls


async def _new_stream() -> Any:
    resp = await chat.stream_chat(ChatRequest(question="pergunta"), authorization="Bearer x")
    return resp.body_iterator


def test_stream_completo_registra_completed_com_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch(monkeypatch, _CHUNKS)

    async def scenario() -> None:
        gen = await _new_stream()
        _ = [chunk async for chunk in gen]  # drena até o fim

    asyncio.run(scenario())
    assert calls == [
        {
            "usage_id": 123,
            "status_value": "completed",
            "answer_chars": 2,
            "prompt_tokens": 10,
            "completion_tokens": 20,
        }
    ]


def test_desconexao_no_fim_conta_como_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cliente recebe a resposta e fecha a conexão ao chegar o 'end'."""
    calls = _patch(monkeypatch, _CHUNKS)

    async def scenario() -> None:
        gen = await _new_stream()
        await gen.__anext__()  # token
        await gen.__anext__()  # end (usage já capturado internamente)
        with pytest.raises(asyncio.CancelledError):
            await gen.athrow(asyncio.CancelledError())

    asyncio.run(scenario())
    assert calls == [
        {
            "usage_id": 123,
            "status_value": "completed",  # <-- antes virava 'cancelled'
            "answer_chars": 2,
            "prompt_tokens": 10,
            "completion_tokens": 20,
        }
    ]


def test_desconexao_no_meio_conta_como_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cliente aborta durante a geração (antes do 'end') → cancelamento real."""
    calls = _patch(monkeypatch, _CHUNKS)

    async def scenario() -> None:
        gen = await _new_stream()
        await gen.__anext__()  # token (ainda não veio usage/end)
        with pytest.raises(asyncio.CancelledError):
            await gen.athrow(asyncio.CancelledError())

    asyncio.run(scenario())
    assert calls == [
        {
            "usage_id": 123,
            "status_value": "cancelled",
            "answer_chars": 2,
            "prompt_tokens": None,
            "completion_tokens": None,
        }
    ]
