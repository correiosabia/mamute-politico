"""Coleção de tarefas de raspagem do Senado."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "parliamentarian": ".parliamentarian",
    "proposition": ".proposition",
    "proposition_status": ".proposition_status",
    "proposition_type": ".proposition_type",
    "roll_call_votes": ".roll_call_votes",
    "speechs_transcipts": ".speechs_transcipts",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(name)

    module = import_module(_EXPORTS[name], __name__)
    return getattr(module, name)

