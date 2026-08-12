"""Feature flags: identificacao de admin sem excecao, resolucao e rotas.

SQLite in-memory com DDL cru e get_db sobrescrito — mesmo padrao de
test_amendments e test_word_cloud_terms.
"""
from __future__ import annotations

from types import SimpleNamespace

from api.security import resolve_ghost_admin


def test_resolve_ghost_admin_sem_authorization_devolve_none():
    request = SimpleNamespace(state=SimpleNamespace())
    assert resolve_ghost_admin(request, None) is None


def test_resolve_ghost_admin_com_token_invalido_devolve_none():
    """Nao levanta: quem so quer saber se exibe uma feature nao merece 404."""
    request = SimpleNamespace(state=SimpleNamespace())
    assert resolve_ghost_admin(request, "Bearer lixo") is None
