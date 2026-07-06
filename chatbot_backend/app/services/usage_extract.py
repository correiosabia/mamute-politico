"""Extração de tokens de uso da resposta do LLM (independente do LangChain).

Isolado em módulo próprio para ser testável sem importar langchain_openai.
"""
from __future__ import annotations

from typing import Any, Optional


def extract_usage(response: Any) -> Optional[dict]:
    """Retorna {prompt_tokens, completion_tokens} de um LLMResult, ou None.

    Tenta `usage_metadata` na mensagem (funciona com stream_usage=True) e,
    como fallback, `llm_output.token_usage`. Nunca levanta (fail-soft).
    """
    try:
        for gen_list in getattr(response, "generations", None) or []:
            for gen in gen_list or []:
                message = getattr(gen, "message", None)
                usage = getattr(message, "usage_metadata", None)
                if usage:
                    return {
                        "prompt_tokens": usage.get("input_tokens"),
                        "completion_tokens": usage.get("output_tokens"),
                    }

        llm_output = getattr(response, "llm_output", None) or {}
        token_usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
        if token_usage:
            return {
                "prompt_tokens": token_usage.get("prompt_tokens"),
                "completion_tokens": token_usage.get("completion_tokens"),
            }
    except Exception:  # noqa: BLE001 — captura de métrica nunca pode quebrar o fluxo
        return None
    return None
