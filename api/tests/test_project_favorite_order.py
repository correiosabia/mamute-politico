"""Ordem pessoal dos parlamentares monitorados — SPEC-001, fatia 1.

Cobre o que a spec promete: a ordem persiste, quem nunca ordenou continua vendo
o comportamento antigo (mais recente primeiro), a lista velha do cliente é
recusada em vez de aplicada pela metade, e ninguém ordena a lista de outro.
"""

from __future__ import annotations

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api import main
from api.dependencies import get_db
from api.routers import projects


def _make_session(favorites: list[tuple[int, int, str]]) -> Session:
    """Cria o banco de teste. `favorites` = (id, parliamentarian_id, created_at)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            create table projetos (
                id integer primary key,
                nome text not null,
                cliente text,
                email text not null,
                tier_id integer,
                tag_ghost text,
                qtd_termos integer not null default 0,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                deleted_at datetime
            )
            """
        )
        conn.exec_driver_sql(
            """
            create table projetos_parliamentarian (
                id integer primary key,
                projeto_id integer not null,
                parliamentarian_id integer not null,
                position integer,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                deleted_at datetime,
                unique (projeto_id, parliamentarian_id)
            )
            """
        )
        for project_id, email in ((10, "assinante@example.com"), (20, "outro@example.com")):
            conn.execute(
                text(
                    """
                    insert into projetos (id, nome, email, qtd_termos, created_at, updated_at)
                    values (:id, :nome, :email, 10, '2026-01-01', '2026-01-01')
                    """
                ),
                {"id": project_id, "nome": f"Projeto {project_id}", "email": email},
            )
        for row_id, parliamentarian_id, created_at in favorites:
            conn.execute(
                text(
                    """
                    insert into projetos_parliamentarian
                        (id, projeto_id, parliamentarian_id, created_at, updated_at)
                    values (:id, 10, :parliamentarian_id, :created_at, :created_at)
                    """
                ),
                {
                    "id": row_id,
                    "parliamentarian_id": parliamentarian_id,
                    "created_at": created_at,
                },
            )
    return Session(engine)


def _client(db: Session, *, token_email: str = "assinante@example.com") -> TestClient:
    app = main.create_app()

    def fake_verify_token(request: Request) -> dict[str, str]:
        request.state.token_email = token_email
        return {"sub": token_email}

    def fake_get_db():
        yield db

    app.dependency_overrides[main.verify_token] = fake_verify_token
    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[projects.get_db] = fake_get_db
    return TestClient(app)


@pytest.fixture()
def db() -> Session:
    # Criados em ordem crescente de data: 303 é o mais recente.
    return _make_session(
        [
            (1, 101, "2026-01-01"),
            (2, 202, "2026-02-01"),
            (3, 303, "2026-03-01"),
        ]
    )


def _listed_ids(client: TestClient) -> list[int]:
    response = client.get("/api/projects/me/favorites")
    assert response.status_code == 200
    return [item["parliamentarian_id"] for item in response.json()]


def test_sem_ordenacao_mantem_comportamento_antigo(db: Session) -> None:
    """position NULL em todos = mais recente primeiro, como antes da SPEC-001."""
    assert _listed_ids(_client(db)) == [303, 202, 101]


def test_reordenar_persiste_a_ordem(db: Session) -> None:
    client = _client(db)

    response = client.patch(
        "/api/projects/me/favorites/order",
        json={"ordered_parliamentarian_ids": [202, 101, 303]},
    )

    assert response.status_code == 200
    assert [item["parliamentarian_id"] for item in response.json()] == [202, 101, 303]
    assert [item["position"] for item in response.json()] == [0, 1, 2]
    # E persiste numa leitura nova, não só no retorno da escrita.
    assert _listed_ids(client) == [202, 101, 303]


def test_lista_desatualizada_e_recusada_sem_escrever(db: Session) -> None:
    """Faltando um id, a ordem do cliente está velha: 422 e nada é gravado."""
    client = _client(db)

    response = client.patch(
        "/api/projects/me/favorites/order",
        json={"ordered_parliamentarian_ids": [202, 101]},
    )

    assert response.status_code == 422
    assert "Atualize a página" in response.json()["detail"]
    assert _listed_ids(client) == [303, 202, 101]


def test_id_repetido_e_recusado(db: Session) -> None:
    client = _client(db)

    response = client.patch(
        "/api/projects/me/favorites/order",
        json={"ordered_parliamentarian_ids": [202, 202, 101]},
    )

    assert response.status_code == 422


def test_id_de_fora_dos_monitorados_e_recusado(db: Session) -> None:
    client = _client(db)

    response = client.patch(
        "/api/projects/me/favorites/order",
        json={"ordered_parliamentarian_ids": [202, 101, 999]},
    )

    assert response.status_code == 422


def test_outro_projeto_nao_ordena_a_lista_alheia(db: Session) -> None:
    """O projeto sai do e-mail do token; o projeto 20 não tem monitorados."""
    client = _client(db, token_email="outro@example.com")

    response = client.patch(
        "/api/projects/me/favorites/order",
        json={"ordered_parliamentarian_ids": [202, 101, 303]},
    )

    assert response.status_code == 422
    # A lista do assinante original segue intacta.
    assert _listed_ids(_client(db)) == [303, 202, 101]


def test_sort_by_explicito_continua_valendo(db: Session) -> None:
    """Cliente que pede outra ordenação não é atropelado pela ordem pessoal."""
    client = _client(db)
    client.patch(
        "/api/projects/me/favorites/order",
        json={"ordered_parliamentarian_ids": [202, 101, 303]},
    )

    response = client.get(
        "/api/projects/me/favorites",
        params={"sort_by": "parliamentarian_id", "sort_order": "asc"},
    )

    assert response.status_code == 200
    assert [item["parliamentarian_id"] for item in response.json()] == [101, 202, 303]


def test_listagem_sobrevive_ao_schema_sem_a_coluna_position() -> None:
    """Janela de deploy: `up.sh` sobe os containers ANTES do `alembic upgrade`.

    Nesse intervalo o código novo consulta o schema antigo. Sem a checagem da
    coluna, o default `sort_by=position` viraria 500 na Seleção e no Dashboard
    de todo assinante — e as feature flags não protegeriam, porque a mudança de
    default é incondicional. Mesmo tratamento que `roll_call_votes` dá a
    `vote_date`.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            create table projetos (
                id integer primary key, nome text not null, cliente text,
                email text not null, tier_id integer, tag_ghost text,
                qtd_termos integer not null default 0,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                deleted_at datetime
            )
            """
        )
        # Schema PRÉ-migração: sem a coluna `position`.
        conn.exec_driver_sql(
            """
            create table projetos_parliamentarian (
                id integer primary key, projeto_id integer not null,
                parliamentarian_id integer not null,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                deleted_at datetime,
                unique (projeto_id, parliamentarian_id)
            )
            """
        )
        conn.exec_driver_sql(
            "insert into projetos (id, nome, email, qtd_termos, created_at, updated_at) "
            "values (10, 'Assinante', 'assinante@example.com', 10, '2026-01-01', '2026-01-01')"
        )
        for row_id, pid, criado in ((1, 101, "2026-01-01"), (2, 202, "2026-02-01")):
            conn.execute(
                text(
                    "insert into projetos_parliamentarian "
                    "(id, projeto_id, parliamentarian_id, created_at, updated_at) "
                    "values (:id, 10, :pid, :c, :c)"
                ),
                {"id": row_id, "pid": pid, "c": criado},
            )
    db = Session(engine)
    client = _client(db)

    resposta = client.get("/api/projects/me/favorites")

    assert resposta.status_code == 200, resposta.text
    # Cai no comportamento anterior: mais recente primeiro.
    assert [f["parliamentarian_id"] for f in resposta.json()] == [202, 101]
