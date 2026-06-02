from __future__ import annotations

from types import SimpleNamespace

from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api import main
from api.dependencies import get_db
from api.routers import projects


def _client_for_authenticated_project(
    monkeypatch,
    *,
    favorite_ids: list[int],
    db_session: Session | None = None,
) -> TestClient:
    app = main.create_app()

    def fake_verify_token(request: Request) -> dict[str, str]:
        request.state.token_email = "assinante@example.com"
        return {"sub": request.state.token_email}

    def fake_get_db():
        yield db_session if db_session is not None else SimpleNamespace()

    monkeypatch.setattr(
        projects,
        "_get_project_from_token_email",
        lambda request, db: SimpleNamespace(id=10, email=request.state.token_email),
    )
    monkeypatch.setattr(
        projects,
        "_get_project_favorite_ids",
        lambda db, project_id: favorite_ids,
    )

    app.dependency_overrides[main.verify_token] = fake_verify_token
    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[projects.get_db] = fake_get_db
    return TestClient(app)


def test_dashboard_activity_is_empty_when_project_has_no_favorites(monkeypatch) -> None:
    client = _client_for_authenticated_project(monkeypatch, favorite_ids=[])

    response = client.get("/api/projects/me/dashboard-activity")

    assert response.status_code == 200
    assert response.json() == {"propositions": [], "votes": []}


def _make_activity_session() -> Session:
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
                type text,
                parliamentarian_code integer,
                name text,
                full_name text,
                email text,
                telephone text,
                cpf text,
                status text,
                party text,
                state_of_birth text,
                city_of_birth text,
                state_elected text,
                site text,
                education text,
                office_name text,
                office_building text,
                office_number text,
                office_floor text,
                office_email text,
                biography_link text,
                biography_text text,
                details text,
                created_at datetime not null,
                updated_at datetime not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            create table proposition (
                id integer primary key,
                proposition_code integer,
                title text,
                link text,
                proposition_acronym text,
                proposition_number integer,
                presentation_year integer,
                agency_id integer,
                proposition_type_id integer,
                proposition_status_id integer,
                current_status text,
                proposition_description text,
                presentation_date date,
                presentation_month integer,
                summary text,
                details text,
                created_at datetime not null,
                updated_at datetime not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            create table authors_proposition (
                id integer primary key,
                parliamentarian_id integer not null,
                proposition_id integer not null,
                created_at datetime not null,
                updated_at datetime not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            create table roll_call_votes (
                id integer primary key,
                parliamentarian_id integer not null,
                proposition_id integer not null,
                vote text,
                description text,
                link text,
                vote_date date,
                created_at datetime not null,
                updated_at datetime not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            insert into parliamentarian
                (id, name, full_name, party, state_elected, created_at, updated_at)
            values
                (101, 'Monitorado', 'Parlamentar Monitorado', 'PMA', 'SP', '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
                (202, 'Outro', 'Parlamentar Fora do Projeto', 'FORA', 'RJ', '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
                (303, 'Coautor', 'Parlamentar Coautor', 'COA', 'MG', '2026-01-01 00:00:00', '2026-01-01 00:00:00')
            """
        )
        conn.exec_driver_sql(
            """
            insert into proposition
                (
                    id,
                    title,
                    link,
                    proposition_acronym,
                    proposition_number,
                    presentation_year,
                    current_status,
                    proposition_description,
                    presentation_date,
                    created_at,
                    updated_at
                )
            values
                (1, 'PL monitorado', 'https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=2293709', 'PL', 1, 2026, 'Aguardando Despacho', 'Do parlamentar monitorado', '2026-05-10', '2026-05-10 00:00:00', '2026-05-10 00:00:00'),
                (2, 'PL fora', null, 'PL', 2, 2026, 'Aguardando Despacho', 'De outro parlamentar', '2026-05-11', '2026-05-11 00:00:00', '2026-05-11 00:00:00'),
                (3, 'PL coautoria', null, 'PL', 3, 2026, 'Aguardando Despacho', 'Com coautoria monitorada', '2026-05-12', '2026-05-12 00:00:00', '2026-05-12 00:00:00')
            """
        )
        conn.exec_driver_sql(
            """
            insert into authors_proposition
                (id, parliamentarian_id, proposition_id, created_at, updated_at)
            values
                (1, 101, 1, '2026-05-10 00:00:00', '2026-05-10 00:00:00'),
                (2, 202, 2, '2026-05-11 00:00:00', '2026-05-11 00:00:00'),
                (3, 303, 3, '2026-05-12 00:00:00', '2026-05-12 00:00:00'),
                (4, 101, 3, '2026-05-12 00:00:00', '2026-05-12 00:00:00')
            """
        )
        conn.exec_driver_sql(
            """
            insert into roll_call_votes
                (id, parliamentarian_id, proposition_id, vote, description, created_at, updated_at)
            values
                (11, 101, 1, 'Sim', 'Voto do monitorado', '2026-05-12 00:00:00', '2026-05-12 00:00:00'),
                (22, 202, 2, 'Não', 'Voto fora do projeto', '2026-05-13 00:00:00', '2026-05-13 00:00:00')
            """
        )
    return Session(engine)


def test_dashboard_activity_only_returns_data_for_project_favorites(monkeypatch) -> None:
    db_session = _make_activity_session()
    try:
        client = _client_for_authenticated_project(
            monkeypatch,
            favorite_ids=[101],
            db_session=db_session,
        )

        response = client.get("/api/projects/me/dashboard-activity")

        assert response.status_code == 200
        payload = response.json()
        assert [item["id"] for item in payload["propositions"]] == [3, 1]
        assert payload["propositions"][0]["monitored_authors"] == [
            {
                "id": 101,
                "name": "Monitorado",
                "full_name": "Parlamentar Monitorado",
                "party": "PMA",
                "state_elected": "SP",
                "type": None,
            }
        ]
        assert [item["id"] for item in payload["votes"]] == [11]
        assert payload["votes"][0]["parliamentarian_name"] == "Parlamentar Monitorado"
        assert (
            payload["votes"][0]["proposition_votes_link"]
            == "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao/votacoes?idProposicao=2293709"
        )
    finally:
        db_session.close()


def test_dashboard_activity_survives_missing_vote_date_migration(monkeypatch) -> None:
    db_session = _make_activity_session()
    try:
        db_session.connection().exec_driver_sql(
            "alter table roll_call_votes drop column vote_date"
        )
        db_session.commit()

        client = _client_for_authenticated_project(
            monkeypatch,
            favorite_ids=[101],
            db_session=db_session,
        )

        response = client.get("/api/projects/me/dashboard-activity")

        assert response.status_code == 200
        payload = response.json()
        assert [item["id"] for item in payload["propositions"]] == [3, 1]
        assert [item["id"] for item in payload["votes"]] == [11]
        assert payload["votes"][0]["date_vote"] is None
        assert payload["votes"][0]["parliamentarian_name"] == "Parlamentar Monitorado"
        assert (
            payload["votes"][0]["proposition_votes_link"]
            == "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao/votacoes?idProposicao=2293709"
        )
    finally:
        db_session.close()


def test_roll_call_votes_survives_missing_vote_date_migration(monkeypatch) -> None:
    db_session = _make_activity_session()
    try:
        db_session.connection().exec_driver_sql(
            "alter table roll_call_votes drop column vote_date"
        )
        db_session.commit()

        client = _client_for_authenticated_project(
            monkeypatch,
            favorite_ids=[101],
            db_session=db_session,
        )

        response = client.get("/api/roll-call-votes/?limit=1&parliamentarian_id=101")

        assert response.status_code == 200
        payload = response.json()
        assert [item["id"] for item in payload] == [11]
        assert payload[0]["date_vote"] is None
        assert payload[0]["parliamentarian_name"] == "Parlamentar Monitorado"
        assert (
            payload[0]["proposition_votes_link"]
            == "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao/votacoes?idProposicao=2293709"
        )
    finally:
        db_session.close()
