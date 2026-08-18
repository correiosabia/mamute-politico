"""Rotas de timeline eleitoral (CS-54).

SQLite in-memory com DDL cru e get_db sobrescrito — mesmo padrão de
test_amendments.py.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api import main
from api.feature_gate import FeatureAccess, trajetoria_access
from api.dependencies import get_db
from api.security import verify_token


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            create table parliamentarian (
                id integer primary key,
                type text, parliamentarian_code integer, name text,
                full_name text, email text, telephone text, cpf text,
                status text, party text, state_of_birth text,
                city_of_birth text, state_elected text, site text,
                education text, office_name text, office_building text,
                office_number text, office_floor text, office_email text,
                biography_link text, biography_text text, details text,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp
            )
            """
        )
        conn.exec_driver_sql(
            """
            create table candidacy (
                id integer primary key,
                election_year integer not null,
                tse_candidate_id integer not null,
                office_code integer, office text, state text,
                ballot_number integer, ballot_name text, full_name text,
                party text, coalition text, status text,
                totalization_status text, cpf text, voter_id text,
                photo_url text, tse_last_update datetime,
                listing_fingerprint text, parliamentarian_id integer,
                match_status text not null, details text,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp
            )
            """
        )
        conn.exec_driver_sql(
            """
            create table electoral_history (
                id integer primary key,
                election_year integer not null,
                tse_candidate_id integer not null,
                tse_election_id integer,
                parliamentarian_id integer,
                candidacy_id integer,
                office text, state text, locality text, party text,
                ballot_name text, full_name text, ballot_number integer,
                result text,
                declared_assets numeric(18,2), assets_count integer,
                assets text, assets_fetched_at datetime,
                source_link text,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp
            )
            """
        )
        conn.exec_driver_sql(
            "insert into parliamentarian (id, name) values (1, 'Sergio Moro'), (2, 'Sem Timeline')"
        )
        conn.exec_driver_sql(
            """
            insert into candidacy
                (id, election_year, tse_candidate_id, office, state,
                 parliamentarian_id, match_status)
            values (10, 2026, 160002540833, 'Governador', 'PR', 1, 'matched_name')
            """
        )
        conn.exec_driver_sql(
            """
            insert into electoral_history
                (election_year, tse_candidate_id, tse_election_id,
                 parliamentarian_id, candidacy_id, office, state, locality,
                 party, ballot_name, result, declared_assets, assets_count,
                 assets, source_link)
            values
                (2026, 160002540833, 20322002026, 1, 10, 'Governador', 'PR',
                 'PARANÁ', 'PL', 'SERGIO MORO', 'Concorrendo', 1036642.25, 12,
                 '[{"valor": 1000.0}]', 'https://tse/2026'),
                (2022, 160001621846, 2040602022, 1, 10, 'Senador', 'PR',
                 'PARANÁ', 'UNIÃO', 'SERGIO MORO', 'Eleito', null, null,
                 null, 'https://tse/2022')
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
    main.app.dependency_overrides[verify_token] = lambda: None
    main.app.dependency_overrides[trajetoria_access] = lambda: FeatureAccess(full=True)
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_timeline_do_parlamentar_ordenada_por_ano_desc(client):
    resp = client.get("/api/parliamentarians/1/electoral-history")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert [e["year"] for e in entries] == [2026, 2022]
    assert "assets" not in entries[0]


def test_declared_assets_trafega_como_string(client):
    entry = client.get("/api/parliamentarians/1/electoral-history").json()["entries"][0]
    assert entry["declared_assets"] == "1036642.25"
    assert entry["result"] == "Concorrendo"


def test_include_assets_traz_a_lista(client):
    resp = client.get(
        "/api/parliamentarians/1/electoral-history",
        params={"include_assets": "true"},
    )
    assert isinstance(resp.json()["entries"][0]["assets"], list)


def test_timeline_da_candidatura(client):
    resp = client.get("/api/candidacies/10/electoral-history")
    assert resp.status_code == 200
    assert len(resp.json()["entries"]) == 2


def test_404_quando_nao_existe(client):
    assert client.get("/api/parliamentarians/999/electoral-history").status_code == 404
    assert client.get("/api/candidacies/999/electoral-history").status_code == 404


def test_lista_vazia_quando_existe_sem_timeline(client):
    resp = client.get("/api/parliamentarians/2/electoral-history")
    assert resp.status_code == 200
    assert resp.json()["entries"] == []
