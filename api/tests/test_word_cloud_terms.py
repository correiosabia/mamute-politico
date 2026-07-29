"""Listas de filtro da nuvem de palavras: leitura pública e escrita admin.

SQLite in-memory, gate e get_db sobrescritos — mesmo padrão de test_admin_tiers.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api import main
from api.dependencies import get_db
from api.security import require_ghost_admin, verify_token


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            create table word_cloud_terms (
                id integer primary key,
                term text not null,
                kind text not null,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                unique (term, kind)
            )
            """
        )
        conn.exec_driver_sql(
            """
            create table admin_audit_log (
                id integer primary key,
                admin_email text not null,
                action text not null,
                entity text not null,
                entity_id text,
                before text,
                after text,
                created_at datetime not null default current_timestamp
            )
            """
        )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


@pytest.fixture()
def session() -> Session:
    s = _make_session()
    yield s
    s.close()


@pytest.fixture()
def client(session: Session) -> TestClient:
    main.app.dependency_overrides[get_db] = lambda: session
    main.app.dependency_overrides[require_ghost_admin] = lambda: "admin@mamute.com"
    # A leitura fica atrás do verify_token (é dado de usuário logado, não público).
    main.app.dependency_overrides[verify_token] = lambda: None
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def _put(client: TestClient, **payload):
    body = {"stopwords": [], "excluded_terms": []}
    body.update(payload)
    return client.put("/api/admin/settings/word-cloud-terms", json=body)


class TestLeitura:
    def test_listas_vazias_quando_nada_configurado(self, client: TestClient) -> None:
        r = client.get("/api/settings/word-cloud-terms")

        assert r.status_code == 200
        assert r.json() == {"stopwords": [], "excluded_terms": []}

    def test_devolve_as_duas_listas_separadas(self, client: TestClient) -> None:
        _put(client, stopwords=["presidente"], excluded_terms=["mudança climática"])

        body = client.get("/api/settings/word-cloud-terms").json()

        assert body["stopwords"] == ["presidente"]
        assert body["excluded_terms"] == ["mudança climática"]

    def test_ordena_alfabeticamente_para_a_tela_ficar_estavel(
        self, client: TestClient
    ) -> None:
        _put(client, stopwords=["senador", "bloco", "presidente"])

        assert client.get("/api/settings/word-cloud-terms").json()["stopwords"] == [
            "bloco",
            "presidente",
            "senador",
        ]


class TestEscrita:
    def test_substitui_as_listas_por_completo(self, client: TestClient) -> None:
        _put(client, stopwords=["presidente", "senador"])
        _put(client, stopwords=["gente"])

        assert client.get("/api/settings/word-cloud-terms").json()["stopwords"] == [
            "gente"
        ]

    def test_normaliza_caixa_e_espacos(self, client: TestClient) -> None:
        _put(client, stopwords=["  PRESIDENTE  ", "Senador"])

        assert client.get("/api/settings/word-cloud-terms").json()["stopwords"] == [
            "presidente",
            "senador",
        ]

    def test_preserva_acentuacao(self, client: TestClient) -> None:
        _put(client, excluded_terms=["Sessão Extraordinária"])

        assert client.get("/api/settings/word-cloud-terms").json()["excluded_terms"] == [
            "sessão extraordinária"
        ]

    def test_deduplica_entradas_equivalentes(self, client: TestClient) -> None:
        _put(client, stopwords=["Presidente", "presidente", " PRESIDENTE "])

        assert client.get("/api/settings/word-cloud-terms").json()["stopwords"] == [
            "presidente"
        ]

    def test_descarta_entradas_vazias(self, client: TestClient) -> None:
        _put(client, stopwords=["presidente", "", "   "])

        assert client.get("/api/settings/word-cloud-terms").json()["stopwords"] == [
            "presidente"
        ]

    def test_mesma_palavra_pode_existir_nas_duas_listas(
        self, client: TestClient
    ) -> None:
        """São filtros diferentes; a UNIQUE é por (termo, tipo)."""

        _put(client, stopwords=["bloco"], excluded_terms=["bloco"])

        body = client.get("/api/settings/word-cloud-terms").json()
        assert body["stopwords"] == ["bloco"]
        assert body["excluded_terms"] == ["bloco"]

    def test_resposta_do_put_traz_o_estado_final(self, client: TestClient) -> None:
        r = _put(client, stopwords=["Senador", "bloco"])

        assert r.status_code == 200
        assert r.json()["stopwords"] == ["bloco", "senador"]


class TestAuditoria:
    def test_registra_quem_alterou_e_o_antes_e_depois(
        self, client: TestClient, session: Session
    ) -> None:
        _put(client, stopwords=["presidente"])
        _put(client, stopwords=["gente"])

        linhas = session.execute(
            __import__("sqlalchemy").text(
                "select admin_email, action, entity, before, after "
                "from admin_audit_log order by id"
            )
        ).all()

        assert len(linhas) == 2
        assert linhas[1][0] == "admin@mamute.com"
        assert linhas[1][1] == "update_word_cloud_terms"
        assert linhas[1][2] == "word_cloud_terms"
        assert "presidente" in linhas[1][3]
        assert "gente" in linhas[1][4]


class TestGateAdmin:
    def test_escrita_nao_existe_para_nao_admin(self, session: Session) -> None:
        """O gate responde 404 para não-admin, sem revelar a rota."""

        from fastapi import HTTPException

        def _nega():
            raise HTTPException(status_code=404, detail="Not Found")

        main.app.dependency_overrides[get_db] = lambda: session
        main.app.dependency_overrides[require_ghost_admin] = _nega
        try:
            r = TestClient(main.app).put(
                "/api/admin/settings/word-cloud-terms",
                json={"stopwords": [], "excluded_terms": []},
            )
            assert r.status_code == 404
        finally:
            main.app.dependency_overrides.clear()
