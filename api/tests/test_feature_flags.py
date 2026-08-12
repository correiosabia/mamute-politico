"""Feature flags: identificacao de admin sem excecao, resolucao e rotas.

SQLite in-memory com DDL cru e get_db sobrescrito — mesmo padrao de
test_amendments e test_word_cloud_terms.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from fastapi.testclient import TestClient

from api import main
from api.dependencies import get_db
from api.security import require_ghost_admin, resolve_ghost_admin, verify_token
from api.services.feature_flags import get_states, resolve_for, set_state


def _session_com_flags(linhas: list[tuple[str, str]]) -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            create table feature_flag (
                key text primary key,
                state text not null default 'off',
                updated_at datetime not null default current_timestamp
            )
            """
        )
        # A escrita de flag e auditada, como toda acao de admin.
        conn.exec_driver_sql(
            """
            create table admin_audit_log (
                id integer primary key,
                admin_email text not null,
                action text not null,
                entity text not null,
                entity_id text,
                "before" text,
                "after" text,
                created_at datetime not null default current_timestamp
            )
            """
        )
        for key, state in linhas:
            conn.exec_driver_sql(
                "insert into feature_flag (key, state) values (?, ?)",
                (key, state),
            )
    return sessionmaker(bind=engine)()


def test_resolve_ghost_admin_sem_authorization_devolve_none():
    request = SimpleNamespace(state=SimpleNamespace())
    assert resolve_ghost_admin(request, None) is None


def test_resolve_ghost_admin_com_token_invalido_devolve_none():
    """Nao levanta: quem so quer saber se exibe uma feature nao merece 404."""
    request = SimpleNamespace(state=SimpleNamespace())
    assert resolve_ghost_admin(request, "Bearer lixo") is None


# --- resolucao do tri-estado ------------------------------------------------


def test_resolve_for_nao_admin():
    db = _session_com_flags([("a", "all"), ("b", "admins"), ("c", "off")])
    assert resolve_for(db, is_admin=False) == {"a": True, "b": False, "c": False}


def test_resolve_for_admin():
    db = _session_com_flags([("a", "all"), ("b", "admins"), ("c", "off")])
    assert resolve_for(db, is_admin=True) == {"a": True, "b": True, "c": False}


def test_get_states_devolve_tri_estado_cru():
    db = _session_com_flags([("a", "all"), ("c", "off")])
    assert get_states(db) == {"a": "all", "c": "off"}


def test_chave_sem_linha_nao_aparece():
    """O front le a ausencia como off; o backend nao inventa a chave."""
    db = _session_com_flags([("a", "all")])
    assert "inexistente" not in resolve_for(db, is_admin=True)


def test_set_state_cria_linha_quando_nao_existe():
    db = _session_com_flags([])
    resultado = set_state(db, "nova", "admins")
    assert resultado["key"] == "nova"
    assert resultado["state"] == "admins"
    assert get_states(db) == {"nova": "admins"}


def test_set_state_atualiza_linha_existente():
    db = _session_com_flags([("a", "off")])
    set_state(db, "a", "all")
    assert get_states(db) == {"a": "all"}


def test_set_state_recusa_estado_invalido():
    db = _session_com_flags([])
    with pytest.raises(ValueError):
        set_state(db, "a", "talvez")


# --- rotas ------------------------------------------------------------------


def _client(linhas: list[tuple[str, str]], admin: bool = False) -> TestClient:
    db = _session_com_flags(linhas)
    app = main.app
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[verify_token] = lambda: {"sub": "u@x.com"}
    if admin:
        app.dependency_overrides[require_ghost_admin] = lambda: "admin@x.com"
    return TestClient(app)


def test_rota_publica_devolve_booleano_resolvido_para_nao_admin():
    try:
        client = _client([("a", "all"), ("b", "admins")])
        r = client.get("/api/settings/feature-flags")
        assert r.status_code == 200
        assert r.json() == {"a": True, "b": False}
    finally:
        main.app.dependency_overrides.clear()


def test_admin_get_devolve_tri_estado_cru():
    try:
        client = _client([("a", "all"), ("b", "admins")], admin=True)
        r = client.get("/api/admin/settings/feature-flags")
        assert r.status_code == 200
        assert [(x["key"], x["state"]) for x in r.json()] == [
            ("a", "all"),
            ("b", "admins"),
        ]
    finally:
        main.app.dependency_overrides.clear()


def test_admin_put_cria_e_atualiza():
    try:
        client = _client([], admin=True)
        r = client.put(
            "/api/admin/settings/feature-flags/nova", json={"state": "all"}
        )
        assert r.status_code == 200
        assert r.json()["state"] == "all"

        r = client.get("/api/admin/settings/feature-flags")
        assert [x["key"] for x in r.json()] == ["nova"]

        r = client.put(
            "/api/admin/settings/feature-flags/nova", json={"state": "off"}
        )
        assert r.json()["state"] == "off"
    finally:
        main.app.dependency_overrides.clear()


def test_admin_put_recusa_estado_invalido():
    try:
        client = _client([], admin=True)
        r = client.put(
            "/api/admin/settings/feature-flags/x", json={"state": "talvez"}
        )
        assert r.status_code == 422
    finally:
        main.app.dependency_overrides.clear()
