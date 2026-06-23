"""Inicialização do aplicativo FastAPI para o chatbot."""

from __future__ import annotations


def create_app(*args, **kwargs):
    from .main import create_app as _create_app

    return _create_app(*args, **kwargs)

__all__ = ["create_app"]
