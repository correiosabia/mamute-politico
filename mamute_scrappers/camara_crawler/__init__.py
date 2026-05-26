"""Scrapers para a Câmara dos Deputados."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "agency": ".agency",
    "parliamentarian": ".parliamentarian",
    "proposition": ".proposition",
    "speeches_transcripts": ".speeches_transcripts",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(name)

    module = import_module(_EXPORTS[name], __name__)
    return getattr(module, name)
