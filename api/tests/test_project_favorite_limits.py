from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api.routers import projects


def _make_session(*, qtd_termos: int, existing_favorites: list[int] | None = None) -> Session:
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
            create table projetos_parliamentarian (
                id integer primary key,
                projeto_id integer not null,
                parliamentarian_id integer not null,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                deleted_at datetime,
                unique (projeto_id, parliamentarian_id)
            )
            """
        )
        conn.execute(
            text(
                """
                insert into projetos
                    (id, nome, email, qtd_termos, created_at, updated_at)
                values
                    (10, 'Assinante', 'assinante@example.com', :qtd_termos, '2026-01-01', '2026-01-01')
                """
            ),
            {"qtd_termos": qtd_termos},
        )
        for parliamentarian_id in [101, 202, 303]:
            conn.execute(
                text(
                    """
                    insert into parliamentarian
                        (id, name, created_at, updated_at)
                    values
                        (:id, :name, '2026-01-01', '2026-01-01')
                    """
                ),
                {"id": parliamentarian_id, "name": f"Parlamentar {parliamentarian_id}"},
            )
        for index, parliamentarian_id in enumerate(existing_favorites or [], start=1):
            conn.execute(
                text(
                    """
                    insert into projetos_parliamentarian
                        (id, projeto_id, parliamentarian_id, created_at, updated_at)
                    values
                        (:id, 10, :parliamentarian_id, '2026-01-01', '2026-01-01')
                    """
                ),
                {"id": index, "parliamentarian_id": parliamentarian_id},
            )
    return Session(engine)


def test_create_project_favorite_allows_new_favorite_below_plan_limit() -> None:
    db = _make_session(qtd_termos=2, existing_favorites=[101])
    try:
        favorite = projects._create_project_favorite(db, 10, 202)

        assert favorite.projeto_id == 10
        assert favorite.parliamentarian_id == 202
        assert projects._get_project_favorite_count(db, 10) == 2
    finally:
        db.close()


def test_create_project_favorite_rejects_new_favorite_at_plan_limit() -> None:
    db = _make_session(qtd_termos=1, existing_favorites=[101])
    try:
        with pytest.raises(HTTPException) as excinfo:
            projects._create_project_favorite(db, 10, 202)

        assert excinfo.value.status_code == 403
        assert "Limite de parlamentares monitorados atingido" in str(excinfo.value.detail)
        assert projects._get_project_favorite_count(db, 10) == 1
    finally:
        db.close()


def test_create_project_favorite_keeps_duplicate_conflict_before_limit() -> None:
    db = _make_session(qtd_termos=1, existing_favorites=[101])
    try:
        with pytest.raises(HTTPException) as excinfo:
            projects._create_project_favorite(db, 10, 101)

        assert excinfo.value.status_code == 409
        assert excinfo.value.detail == "Parlamentar já está favoritado neste projeto."
    finally:
        db.close()


def test_project_favorite_quota_reports_limit_used_and_remaining() -> None:
    db = _make_session(qtd_termos=3, existing_favorites=[101, 202])
    try:
        project = projects._ensure_active_project(db, 10)
        quota = projects._build_project_favorite_quota(db, project)

        assert quota.limit == 3
        assert quota.used == 2
        assert quota.remaining == 1
        assert quota.limit_reached is False
    finally:
        db.close()
