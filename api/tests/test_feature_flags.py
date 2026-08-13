"""Feature flags: identificacao de admin sem excecao, resolucao e rotas.

SQLite in-memory com DDL cru e get_db sobrescrito — mesmo padrao de
test_amendments e test_word_cloud_terms.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from fastapi import Request
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
        conn.exec_driver_sql(
            """
            create table tiers (
                id integer primary key,
                tier_name_debug text not null,
                product_id text not null unique,
                detalhes text not null default '{}',
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                deleted_at datetime
            )
            """
        )
        conn.exec_driver_sql(
            """
            create table feature_flag_tier (
                flag_key text not null,
                tier_id integer not null,
                created_at datetime not null default current_timestamp,
                primary key (flag_key, tier_id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            create table projetos (
                id integer primary key,
                nome text not null,
                cliente text,
                email text not null,
                tier_id integer,
                tag_ghost text,
                qtd_termos integer,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                deleted_at datetime
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


def test_all_sem_plano_liberado_nao_aparece():
    """`all` nao e "todo mundo ve": e "agora quem decide e o plano"."""
    db = _session_com_flags([("a", "all"), ("b", "admins"), ("c", "off")])
    assert resolve_for(db, is_admin=False, liberadas=set()) == {
        "a": False,
        "b": False,
        "c": False,
    }


def test_all_com_plano_liberado_aparece():
    db = _session_com_flags([("a", "all"), ("b", "admins"), ("c", "off")])
    assert resolve_for(db, is_admin=False, liberadas={"a"}) == {
        "a": True,
        "b": False,
        "c": False,
    }


def test_plano_nao_libera_flag_que_ainda_esta_em_admins():
    """O tri-estado manda: plano ligado nao adianta antes do lancamento."""
    db = _session_com_flags([("b", "admins")])
    assert resolve_for(db, is_admin=False, liberadas={"b"}) == {"b": False}


def test_plano_nao_libera_flag_desligada_no_global():
    db = _session_com_flags([("c", "off")])
    assert resolve_for(db, is_admin=False, liberadas={"c"}) == {"c": False}


def test_admin_ve_sem_depender_do_plano():
    db = _session_com_flags([("a", "all"), ("b", "admins"), ("c", "off")])
    assert resolve_for(db, is_admin=True, liberadas=set()) == {
        "a": True,
        "b": True,
        "c": False,
    }


def test_sem_plano_nenhum_nao_ve_feature_de_plano():
    """Usuario sem projeto/tier: falha fechado."""
    db = _session_com_flags([("a", "all")])
    assert resolve_for(db, is_admin=False, liberadas=None) == {"a": False}


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


def _client(
    linhas: list[tuple[str, str]],
    admin: bool = False,
    features_do_plano: list[str] | None = None,
) -> TestClient:
    db = _session_com_flags(linhas)
    if features_do_plano is not None:
        db.execute(
            text(
                "insert into tiers (id, tier_name_debug, product_id, detalhes)"
                " values (1, 'Basico', 'prod_1', '{}')"
            )
        )
        db.execute(
            text(
                "insert into projetos (id, nome, email, tier_id)"
                " values (1, 'Projeto', 'u@x.com', 1)"
            )
        )
        for chave in features_do_plano:
            db.execute(
                text(
                    "insert into feature_flag_tier (flag_key, tier_id)"
                    " values (:k, 1)"
                ),
                {"k": chave},
            )
        db.commit()
    app = main.app
    app.dependency_overrides[get_db] = lambda: db

    # O verify_token real popula request.state.token_email; o override precisa
    # fazer o mesmo, porque e dali que a rota tira o plano do chamador.
    def _fake_verify(request: Request) -> dict:
        request.state.token_payload = {"sub": "u@x.com"}
        request.state.token_email = "u@x.com"
        return {"sub": "u@x.com"}

    app.dependency_overrides[verify_token] = _fake_verify
    if admin:
        app.dependency_overrides[require_ghost_admin] = lambda: "admin@x.com"
    return TestClient(app)


def test_rota_publica_resolve_pelo_plano_do_chamador():
    try:
        client = _client(
            [("a", "all"), ("b", "all")], features_do_plano=["a"]
        )
        r = client.get("/api/settings/feature-flags")
        assert r.status_code == 200
        # `a` esta ligada no plano; `b` esta em `all` mas o plano nao a tem.
        assert r.json() == {"a": True, "b": False}
    finally:
        main.app.dependency_overrides.clear()


def test_rota_publica_sem_plano_vinculado_nao_quebra():
    """Vinculo quebrado nao pode virar erro numa chamada que so decide o que
    renderizar: falha fechado."""
    try:
        client = _client([("a", "all")])
        r = client.get("/api/settings/feature-flags")
        assert r.status_code == 200
        assert r.json() == {"a": False}
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


def test_admin_get_traz_contagem_de_planos_ligados():
    """Flag em `all` com zero planos nao aparece para ninguem — a tela precisa
    conseguir denunciar isso."""
    try:
        client = _client([("a", "all")], admin=True, features_do_plano=["a"])
        r = client.get("/api/admin/settings/feature-flags")
        assert r.status_code == 200
        linha = r.json()[0]
        assert linha["tiers_ligados"] == 1
        assert linha["tiers_total"] == 1
    finally:
        main.app.dependency_overrides.clear()


def test_admin_get_denuncia_flag_liberada_sem_nenhum_plano():
    try:
        client = _client([("a", "all")], admin=True, features_do_plano=[])
        r = client.get("/api/admin/settings/feature-flags")
        linha = r.json()[0]
        assert linha["state"] == "all"
        assert linha["tiers_ligados"] == 0
        assert linha["tiers_total"] == 1
    finally:
        main.app.dependency_overrides.clear()


# --- recorte por plano, editado na tela de tiers ----------------------------


def test_tier_features_substitui_a_lista_inteira():
    """A tela edita a lista do plano e salva de uma vez, como word_cloud_terms."""
    try:
        client = _client([("a", "all"), ("b", "all")], admin=True, features_do_plano=["a"])
        r = client.put("/api/admin/tiers/1/features", json={"features": ["b"]})
        assert r.status_code == 200
        assert r.json() == {"tier_id": 1, "features": ["b"]}

        r = client.get("/api/admin/tiers/1/features")
        assert r.json()["features"] == ["b"]
    finally:
        main.app.dependency_overrides.clear()


def test_tier_features_lista_vazia_desliga_tudo():
    try:
        client = _client([("a", "all")], admin=True, features_do_plano=["a"])
        r = client.put("/api/admin/tiers/1/features", json={"features": []})
        assert r.json()["features"] == []
    finally:
        main.app.dependency_overrides.clear()


def test_tier_features_404_para_plano_inexistente():
    try:
        client = _client([], admin=True, features_do_plano=[])
        r = client.put("/api/admin/tiers/999/features", json={"features": []})
        assert r.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


def test_plano_novo_nasce_sem_nenhuma_feature():
    """Sem linha em feature_flag_tier, o plano nao ve feature nenhuma — e por
    isso que plano vindo do sync do Ghost nasce desligado."""
    try:
        client = _client([("a", "all")], features_do_plano=[])
        r = client.get("/api/settings/feature-flags")
        assert r.json() == {"a": False}
    finally:
        main.app.dependency_overrides.clear()
