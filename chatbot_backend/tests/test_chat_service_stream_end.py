"""O stream do serviço emite tokens, usage e end a partir de chain.astream().

Bug real de prod (02/08/2026): o padrão antigo (ainvoke em task +
AsyncIteratorCallbackHandler embrulhado em handler custom) parou de streamar em
silêncio — o LangChain não reconhecia o wrapper como streaming handler, a
chamada virava não-streaming e NENHUM evento 'token' era emitido, embora o
'usage' registrasse a resposta gerada (chatbot_usage ficava com completed e
answer_chars=0). O serviço agora consome chain.astream() diretamente; estes
testes cobrem o contrato de eventos sem stubar o serviço inteiro.
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

import pytest

from chatbot_backend.app.services import chat_service

_TIMEOUT = 5


class _Chunk:
    """Simula um AIMessageChunk (content + usage_metadata no chunk final)."""

    def __init__(self, content: str = "", usage_metadata: dict | None = None) -> None:
        self.content = content
        self.usage_metadata = usage_metadata


class _FakeChain:
    def __init__(self, chunks: list[_Chunk], fail: bool = False) -> None:
        self._chunks = chunks
        self._fail = fail

    async def astream(self, inputs: dict[str, Any]) -> AsyncIterator[_Chunk]:
        for chunk in self._chunks:
            yield chunk
            await asyncio.sleep(0)
        if self._fail:
            raise RuntimeError("boom")


def _service_with_chain(monkeypatch: pytest.MonkeyPatch, chain: _FakeChain) -> Any:
    service = chat_service.ChatbotService()
    monkeypatch.setattr(service, "_build_chain", lambda: chain)
    return service


def _collect(service: Any, request_id: str) -> list[dict[str, Any]]:
    async def scenario() -> list[dict[str, Any]]:
        chunks = []
        async for chunk in service.stream_response(
            {"question": "q", "history": []}, request_id=request_id
        ):
            chunks.append(chunk)
        return chunks

    return asyncio.run(asyncio.wait_for(scenario(), timeout=_TIMEOUT))


def test_stream_emite_tokens_usage_e_end(monkeypatch: pytest.MonkeyPatch) -> None:
    chain = _FakeChain(
        [
            _Chunk("Olá"),
            _Chunk(" mundo"),
            _Chunk("", usage_metadata={"input_tokens": 7, "output_tokens": 3}),
        ]
    )
    service = _service_with_chain(monkeypatch, chain)

    chunks = _collect(service, "t-ok")
    assert chunks[:2] == [
        {"type": "token", "value": "Olá"},
        {"type": "token", "value": " mundo"},
    ]
    assert {"type": "usage", "prompt_tokens": 7, "completion_tokens": 3} in chunks
    assert chunks[-1] == {"type": "end"}


def test_chunks_vazios_nao_viram_eventos_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chunks sem conteúdo (ex.: só usage) não podem gerar 'token' vazio."""
    chain = _FakeChain(
        [
            _Chunk(""),
            _Chunk("resposta"),
            _Chunk("", usage_metadata={"input_tokens": 1, "output_tokens": 2}),
        ]
    )
    service = _service_with_chain(monkeypatch, chain)

    chunks = _collect(service, "t-empty-chunks")
    tokens = [c for c in chunks if c["type"] == "token"]
    assert tokens == [{"type": "token", "value": "resposta"}]


def test_stream_sem_conteudo_ainda_emite_usage_e_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resposta vazia do provedor: o stream fecha normalmente (front trata)."""
    chain = _FakeChain([_Chunk("", usage_metadata={"input_tokens": 5, "output_tokens": 0})])
    service = _service_with_chain(monkeypatch, chain)

    chunks = _collect(service, "t-empty")
    assert chunks == [
        {"type": "usage", "prompt_tokens": 5, "completion_tokens": 0},
        {"type": "end"},
    ]


def test_stream_com_erro_do_llm_nao_pendura(monkeypatch: pytest.MonkeyPatch) -> None:
    chain = _FakeChain([_Chunk("parcial")], fail=True)
    service = _service_with_chain(monkeypatch, chain)

    async def scenario() -> None:
        async for _ in service.stream_response(
            {"question": "q", "history": []}, request_id="t-err"
        ):
            pass

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(asyncio.wait_for(scenario(), timeout=_TIMEOUT))
