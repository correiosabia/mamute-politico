"""Auditoria admin das emendas que não casaram com nenhum parlamentar."""
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
            create table parliamentary_amendment (
                id integer primary key,
                amendment_code text not null unique,
                year integer,
                amendment_number text,
                amendment_type text,
                author_name_raw text,
                author_raw text,
                parliamentarian_id integer,
                match_status text not null,
                spending_locality text,
                function text,
                subfunction text,
                committed_value numeric(18,2),
                settled_value numeric(18,2),
                paid_value numeric(18,2),
                remainder_inscribed numeric(18,2),
                remainder_cancelled numeric(18,2),
                remainder_paid numeric(18,2),
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp
            )
            """
        )
        # Nomes reais que não casaram no diagnóstico contra a fonte.
        conn.exec_driver_sql(
            """
            insert into parliamentary_amendment
                (amendment_code, year, author_name_raw, parliamentarian_id,
                 match_status, committed_value)
            values
                ('A1', 2026, 'FATIMA PELAES', null, 'unmatched', 1000.00),
                ('A2', 2026, 'FATIMA PELAES', null, 'unmatched', 2000.00),
                ('A3', 2026, 'JOAO SILVA', null, 'ambiguous', 500.00),
                ('A4', 2026, 'HEITOR SCHUCH', 1, 'matched', 999999.00)
            """
        )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


@pytest.fixture()
def session() -> Session:
    s = _make_session()
    yield s
    s.close()


@pytest.fixture()
def admin_client(session: Session) -> TestClient:
    main.app.dependency_overrides[get_db] = lambda: session
    main.app.dependency_overrides[require_ghost_admin] = lambda: "admin@mamute.com"
    main.app.dependency_overrides[verify_token] = lambda: None
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


@pytest.fixture()
def anon_client(session: Session) -> TestClient:
    # Sem override de require_ghost_admin: o gate real responde para não-admin.
    main.app.dependency_overrides[get_db] = lambda: session
    main.app.dependency_overrides[verify_token] = lambda: None
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_agrupa_por_autor_e_soma(admin_client):
    resp = admin_client.get("/api/admin/amendments/unmatched")
    assert resp.status_code == 200
    linhas = {item["author_name_raw"]: item for item in resp.json()}

    assert linhas["FATIMA PELAES"]["amendment_count"] == 2
    assert linhas["FATIMA PELAES"]["committed_total"] == "3000.00"
    assert linhas["FATIMA PELAES"]["match_status"] == "unmatched"


def test_inclui_ambiguous_alem_de_unmatched(admin_client):
    nomes = {
        item["author_name_raw"]
        for item in admin_client.get("/api/admin/amendments/unmatched").json()
    }
    assert "JOAO SILVA" in nomes


def test_exclui_o_que_ja_casou(admin_client):
    nomes = {
        item["author_name_raw"]
        for item in admin_client.get("/api/admin/amendments/unmatched").json()
    }
    assert "HEITOR SCHUCH" not in nomes


def test_ordena_pelo_maior_valor_primeiro(admin_client):
    totais = [
        float(item["committed_total"])
        for item in admin_client.get("/api/admin/amendments/unmatched").json()
    ]
    assert totais == sorted(totais, reverse=True)


def test_nao_admin_nao_acessa(anon_client):
    resp = anon_client.get("/api/admin/amendments/unmatched")
    assert resp.status_code != 200
