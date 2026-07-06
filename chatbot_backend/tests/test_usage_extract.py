"""Extração de tokens da resposta do LLM (duck-typed, sem langchain)."""
from __future__ import annotations

from chatbot_backend.app.services.usage_extract import extract_usage


class _Msg:
    def __init__(self, um):
        self.usage_metadata = um


class _Gen:
    def __init__(self, um):
        self.message = _Msg(um)


class _Result:
    def __init__(self, um=None, llm_output=None):
        self.generations = [[_Gen(um)]] if um is not None else []
        self.llm_output = llm_output or {}


def test_extract_from_usage_metadata() -> None:
    r = _Result(um={"input_tokens": 12, "output_tokens": 34})
    assert extract_usage(r) == {"prompt_tokens": 12, "completion_tokens": 34}


def test_extract_from_llm_output_fallback() -> None:
    r = _Result(llm_output={"token_usage": {"prompt_tokens": 5, "completion_tokens": 7}})
    assert extract_usage(r) == {"prompt_tokens": 5, "completion_tokens": 7}


def test_extract_none_when_absent() -> None:
    assert extract_usage(object()) is None
    assert extract_usage(_Result()) is None
