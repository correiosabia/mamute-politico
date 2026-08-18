"""Feature flags: identificacao de admin sem excecao, resolucao e rotas.

SQLite in-memory com DDL cru e get_db sobrescrito — mesmo padrao de
test_amendments e test_word_cloud_terms.

Desde a CS-58 a resolucao e tri-valorada ('liberada' | 'bloqueada' |
'oculta') e o vinculo plano x feature carrega um modo ('liberado' |
'cadeado'; ausencia = oculto).
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
from api.services.feature_flags import (
    enabled_flags_for_tier,
    get_states,
    resolve_for,
    set_state,
    set_tier_flags,
)


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
                mode text not null default 'liberado',
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


# --- resolucao do tri-estado + modo do plano --------------------------------


def test_all_sem_plano_fica_oculta():
    """`all` nao e "todo mundo ve": e "agora quem decide e o plano"."""
    db = _session_com_flags([("a", "all"), ("b", "admins"), ("c", "off")])
    assert resolve_for(db, is_admin=False, modos={}) == {
        "a": "oculta",
        "b": "oculta",
        "c": "oculta",
    }


def test_all_com_modo_liberado_resolve_liberada():
    db = _session_com_flags([("a", "all"), ("b", "admins"), ("c", "off")])
    assert resolve_for(db, is_admin=False, modos={"a": "liberado"}) == {
        "a": "liberada",
        "b": "oculta",
        "c": "oculta",
    }


def test_all_com_modo_cadeado_resolve_bloqueada():
    """O cerne da CS-58: plano sem o recurso, mas com vitrine."""
    db = _session_com_flags([("a", "all")])
    assert resolve_for(db, is_admin=False, modos={"a": "cadeado"}) == {
        "a": "bloqueada"
    }


def test_admins_nao_vira_cadeado_para_nao_admin():
    """Recurso nao lancado nao vira vitrine: cadeado so existe em `all`."""
    db = _session_com_flags([("b", "admins")])
    assert resolve_for(db, is_admin=False, modos={"b": "cadeado"}) == {
        "b": "oculta"
    }


def test_plano_nao_libera_flag_desligada_no_global():
    db = _session_com_flags([("c", "off")])
    assert resolve_for(db, is_admin=False, modos={"c": "liberado"}) == {
        "c": "oculta"
    }


def test_admin_resolve_liberada_para_tudo_menos_off():
    db = _session_com_flags([("a", "all"), ("b", "admins"), ("c", "off")])
    assert resolve_for(db, is_admin=True, modos={}) == {
        "a": "liberada",
        "b": "liberada",
        "c": "oculta",
    }


def test_sem_plano_nenhum_nao_ve_feature_de_plano():
    """Usuario sem projeto/tier: falha fechado."""
    db = _session_com_flags([("a", "all")])
    assert resolve_for(db, is_admin=False, modos=None) == {"a": "oculta"}


def test_get_states_devolve_tri_estado_cru():
    db = _session_com_flags([("a", "all"), ("c", "off")])
    assert get_states(db) == {"a": "all", "c": "off"}


def test_chave_sem_linha_nao_aparece():
    """O front le a ausencia como oculta; o backend nao inventa a chave."""
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


# --- servicos do vinculo plano x feature ------------------------------------


def _com_tier(db: Session, tier_id: int = 1) -> Session:
    db.execute(
        text(
            "insert into tiers (id, tier_name_debug, product_id, detalhes)"
            f" values ({tier_id}, 'Basico', 'prod_{tier_id}', '{{}}')"
        )
    )
    return db


def test_enabled_flags_for_tier_devolve_modos():
    db = _com_tier(_session_com_flags([("a", "all"), ("b", "all")]))
    db.execute(
        text(
            "insert into feature_flag_tier (flag_key, tier_id, mode)"
            " values ('a', 1, 'liberado'), ('b', 1, 'cadeado')"
        )
    )
    assert enabled_flags_for_tier(db, 1) == {"a": "liberado", "b": "cadeado"}


def test_enabled_flags_sem_tier_devolve_vazio():
    db = _session_com_flags([])
    assert enabled_flags_for_tier(db, None) == {}


def test_set_tier_flags_grava_e_substitui_modos():
    db = _com_tier(_session_com_flags([]))
    set_tier_flags(db, 1, {"a": "liberado", "b": "cadeado"})
    assert enabled_flags_for_tier(db, 1) == {"a": "liberado", "b": "cadeado"}
    # Substitui por completo: quem sai, sai; quem muda de modo, muda.
    set_tier_flags(db, 1, {"b": "liberado"})
    assert enabled_flags_for_tier(db, 1) == {"b": "liberado"}


def test_set_tier_flags_recusa_modo_invalido():
    db = _com_tier(_session_com_flags([]))
    with pytest.raises(ValueError):
        set_tier_flags(db, 1, {"a": "gratis"})


# --- rotas ------------------------------------------------------------------


def _client(
    linhas: list[tuple[str, str]],
    admin: bool = False,
    plano_com: dict[str, str] | None = None,
) -> TestClient:
    db = _session_com_flags(linhas)
    if plano_com is not None:
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
        for chave, modo in plano_com.items():
            db.execute(
                text(
                    "insert into feature_flag_tier (flag_key, tier_id, mode)"
                    " values (:k, 1, :m)"
                ),
                {"k": chave, "m": modo},
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
            [("a", "all"), ("b", "all")], plano_com={"a": "liberado"}
        )
        r = client.get("/api/settings/feature-flags")
        assert r.status_code == 200
        # `a` liberada no plano; `b` em `all` mas o plano nao a tem.
        assert r.json() == {"a": "liberada", "b": "oculta"}
    finally:
        main.app.dependency_overrides.clear()


def test_rota_publica_devolve_bloqueada_para_plano_com_cadeado():
    try:
        client = _client([("a", "all")], plano_com={"a": "cadeado"})
        r = client.get("/api/settings/feature-flags")
        assert r.status_code == 200
        assert r.json() == {"a": "bloqueada"}
    finally:
        main.app.dependency_overrides.clear()


def test_rota_publica_sem_plano_vinculado_nao_quebra():
    """Vinculo quebrado nao pode virar erro numa chamada que so decide o que
    renderizar: falha fechado."""
    try:
        client = _client([("a", "all")])
        r = client.get("/api/settings/feature-flags")
        assert r.status_code == 200
        assert r.json() == {"a": "oculta"}
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


def test_admin_get_traz_contagem_por_modo():
    """Flag em `all` com zero planos nao aparece para ninguem — a tela precisa
    conseguir denunciar isso, agora distinguindo liberado de cadeado."""
    try:
        client = _client(
            [("a", "all")], admin=True, plano_com={"a": "cadeado"}
        )
        r = client.get("/api/admin/settings/feature-flags")
        assert r.status_code == 200
        linha = r.json()[0]
        assert linha["tiers_liberados"] == 0
        assert linha["tiers_cadeado"] == 1
        assert linha["tiers_total"] == 1
    finally:
        main.app.dependency_overrides.clear()


def test_admin_get_denuncia_flag_liberada_sem_nenhum_plano():
    try:
        client = _client([("a", "all")], admin=True, plano_com={})
        r = client.get("/api/admin/settings/feature-flags")
        linha = r.json()[0]
        assert linha["state"] == "all"
        assert linha["tiers_liberados"] == 0
        assert linha["tiers_cadeado"] == 0
        assert linha["tiers_total"] == 1
    finally:
        main.app.dependency_overrides.clear()


# --- recorte por plano, editado na tela de tiers ----------------------------


def test_tier_features_substitui_o_mapa_inteiro():
    """A tela edita o mapa do plano e salva de uma vez, como word_cloud_terms."""
    try:
        client = _client(
            [("a", "all"), ("b", "all")],
            admin=True,
            plano_com={"a": "liberado"},
        )
        r = client.put(
            "/api/admin/tiers/1/features",
            json={"features": {"b": "cadeado"}},
        )
        assert r.status_code == 200
        assert r.json() == {"tier_id": 1, "features": {"b": "cadeado"}}

        r = client.get("/api/admin/tiers/1/features")
        assert r.json()["features"] == {"b": "cadeado"}
    finally:
        main.app.dependency_overrides.clear()


def test_tier_features_mapa_vazio_desliga_tudo():
    try:
        client = _client(
            [("a", "all")], admin=True, plano_com={"a": "liberado"}
        )
        r = client.put("/api/admin/tiers/1/features", json={"features": {}})
        assert r.json()["features"] == {}
    finally:
        main.app.dependency_overrides.clear()


def test_tier_features_recusa_modo_invalido():
    try:
        client = _client([("a", "all")], admin=True, plano_com={})
        r = client.put(
            "/api/admin/tiers/1/features", json={"features": {"a": "gratis"}}
        )
        assert r.status_code == 422
    finally:
        main.app.dependency_overrides.clear()


def test_tier_features_404_para_plano_inexistente():
    try:
        client = _client([], admin=True, plano_com={})
        r = client.put(
            "/api/admin/tiers/999/features", json={"features": {}}
        )
        assert r.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


def test_plano_novo_nasce_sem_nenhuma_feature():
    """Sem linha em feature_flag_tier, o plano nao ve feature nenhuma — e por
    isso que plano vindo do sync do Ghost nasce desligado."""
    try:
        client = _client([("a", "all")], plano_com={})
        r = client.get("/api/settings/feature-flags")
        assert r.json() == {"a": "oculta"}
    finally:
        main.app.dependency_overrides.clear()
