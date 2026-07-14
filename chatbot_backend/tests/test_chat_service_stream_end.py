"""O stream do serviço TERMINA e emite usage+end quando o LLM conclui.

Bug real de prod: JSONTokenStreamingHandler é o único callback do chain e não
repassava on_llm_end/on_llm_error ao AsyncIteratorCallbackHandler — o `done`
nunca era setado, o aiter() ficava pendurado para sempre depois do último
token e o fluxo nunca emitia 'usage'/'end'. Resultado: toda consulta real
era registrada como 'cancelled' sem tokens quando o cliente desistia da
conexão (a resposta já tinha sido entregue). Os testes da PR #117 não
pegaram porque stubavam o serviço inteiro.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from chatbot_backend.app.services import chat_service

_TIMEOUT = 5  # com o bug, o stream pendura para sempre; 5s é folga suficiente


def _fake_llm_result() -> Any:
    class _Msg:
        usage_metadata = {"input_tokens": 7, "output_tokens": 3}

    class _Gen:
        message = _Msg()

    class _Result:
        generations = [[_Gen()]]
        llm_output: dict[str, Any] = {}

    return _Result()


class _FakeChain:
    """Simula o ciclo de vida do LangChain via callbacks (como em produção)."""

    def __init__(self, fail: bool = False) -> None:
        self._fail = fail

    async def ainvoke(self, inputs: dict[str, Any], config: dict | None = None) -> str:
        handler = (config or {}).get("callbacks", [None])[0]
        # sleep entre tokens: como em produção (rede), o consumidor drena a
        # fila antes do fim — evita a corrida token-vs-done do aiter().
        await handler.on_llm_new_token("Olá", run_id="r1")
        await asyncio.sleep(0.01)
        await handler.on_llm_new_token(" mundo", run_id="r1")
        await asyncio.sleep(0.01)
        if self._fail:
            error = RuntimeError("boom")
            await handler.on_llm_error(error)
            raise error
        await handler.on_llm_end(_fake_llm_result())
        return "ok"


def _service_with_chain(monkeypatch: pytest.MonkeyPatch, chain: _FakeChain) -> Any:
    service = chat_service.ChatbotService()
    monkeypatch.setattr(service, "_build_chain", lambda: chain)
    return service


def test_stream_termina_e_emite_usage_e_end(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_chain(monkeypatch, _FakeChain())

    async def scenario() -> list[dict[str, Any]]:
        chunks = []
        async for chunk in service.stream_response(
            {"question": "q", "history": []}, request_id="t-ok"
        ):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(asyncio.wait_for(scenario(), timeout=_TIMEOUT))
    assert [c["type"] for c in chunks[:2]] == ["token", "token"]
    assert {"type": "usage", "prompt_tokens": 7, "completion_tokens": 3} in chunks
    assert chunks[-1] == {"type": "end"}


def test_stream_com_erro_do_llm_nao_pendura(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_chain(monkeypatch, _FakeChain(fail=True))

    async def scenario() -> None:
        async for _ in service.stream_response(
            {"question": "q", "history": []}, request_id="t-err"
        ):
            pass

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(asyncio.wait_for(scenario(), timeout=_TIMEOUT))
