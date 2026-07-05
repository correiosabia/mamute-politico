"""CRUD admin de tiers + auditoria. SQLite in-memory, gate e get_db sobrescritos."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api import main
from api.dependencies import get_db
from api.security import require_ghost_admin


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            create table tiers (
                id integer primary key,
                tier_name_debug text not null,
                product_id text not null,
                detalhes text not null,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                deleted_at datetime
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
        conn.exec_driver_sql(
            "insert into tiers (id, tier_name_debug, product_id, detalhes) "
            "values (1, 'Cidadão', 'cidadao-mamute', :d)",
            {"d": json.dumps({"qtd_termos": 10, "qtd_consultas_ia_mes": 200})},
        )
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


@pytest.fixture()
def client() -> TestClient:
    session = _make_session()

    def _override_get_db():
        try:
            yield session
        finally:
            pass

    main.app.dependency_overrides[get_db] = _override_get_db
    main.app.dependency_overrides[require_ghost_admin] = lambda: "admin@x.com"
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()
    session.close()


def test_list_tiers(client: TestClient) -> None:
    resp = client.get("/api/admin/tiers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["product_id"] == "cidadao-mamute"
    assert data[0]["detalhes"]["qtd_termos"] == 10


def test_update_tier_merges_and_audits(client: TestClient) -> None:
    resp = client.put(
        "/api/admin/tiers/1",
        json={"qtd_consultas_ia_mes": 500, "preco_mensal": 49.9},
    )
    assert resp.status_code == 200
    body = resp.json()
    # merge: mantém qtd_termos, atualiza a consulta e adiciona preço
    assert body["detalhes"]["qtd_termos"] == 10
    assert body["detalhes"]["qtd_consultas_ia_mes"] == 500
    assert body["detalhes"]["preco_mensal"] == 49.9

    # segunda chamada: confere persistência + auditoria
    again = client.get("/api/admin/tiers").json()
    assert again[0]["detalhes"]["qtd_consultas_ia_mes"] == 500


def test_update_rejects_negative(client: TestClient) -> None:
    resp = client.put("/api/admin/tiers/1", json={"qtd_termos": -3})
    assert resp.status_code == 422


def test_update_unknown_tier_404(client: TestClient) -> None:
    resp = client.put("/api/admin/tiers/999", json={"qtd_termos": 5})
    assert resp.status_code == 404
