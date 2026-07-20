from __future__ import annotations

import json

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api import main
from api.dependencies import get_db
from api.routers import projects


# Tipos por parlamentar usados nas fixtures: câmara (deputado) e senado (senador).
_PARLIAMENTARIAN_TYPES = {
    101: "Deputado",
    202: "Deputado",
    303: "Senador",
    404: "Senador",
}


@pytest.fixture(autouse=True)
def _clear_limit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAMUTE_TIER_LIMITS_JSON", raising=False)


def _make_session(
    *,
    qtd_termos: int = 0,
    qtd_termos_camara: int | None = None,
    qtd_termos_senado: int | None = None,
    existing_favorites: list[int] | None = None,
    tier_slug: str = "default-product",
    product_id: str = "target-tier-id",
) -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    detalhes: dict = {"ghost": {"slug": tier_slug}}
    if qtd_termos_camara is not None:
        detalhes["qtd_termos_camara"] = qtd_termos_camara
    if qtd_termos_senado is not None:
        detalhes["qtd_termos_senado"] = qtd_termos_senado
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
                insert into tiers
                    (id, tier_name_debug, product_id, detalhes, created_at, updated_at)
                values
                    (1, 'Plano teste', :product_id, :detalhes, '2026-01-01', '2026-01-01')
                """
            ),
            {"product_id": product_id, "detalhes": json.dumps(detalhes)},
        )
        conn.execute(
            text(
                """
                insert into projetos
                    (id, nome, cliente, email, tier_id, qtd_termos, created_at, updated_at)
                values
                    (10, 'Assinante', :product_id, 'assinante@example.com', 1, :qtd_termos,
                     '2026-01-01', '2026-01-01')
                """
            ),
            {"product_id": product_id, "qtd_termos": qtd_termos},
        )
        for parliamentarian_id, ptype in _PARLIAMENTARIAN_TYPES.items():
            conn.execute(
                text(
                    """
                    insert into parliamentarian
                        (id, type, name, created_at, updated_at)
                    values
                        (:id, :type, :name, '2026-01-01', '2026-01-01')
                    """
                ),
                {
                    "id": parliamentarian_id,
                    "type": ptype,
                    "name": f"Parlamentar {parliamentarian_id}",
                },
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


def _add_project(
    db: Session,
    *,
    project_id: int,
    email: str,
    qtd_termos: int = 3,
) -> None:
    db.execute(
        text(
            """
            insert into projetos
                (id, nome, cliente, email, tier_id, qtd_termos, created_at, updated_at)
            values
                (:project_id, :nome, 'target-tier-id', :email, 1, :qtd_termos,
                 '2026-01-01', '2026-01-01')
            """
        ),
        {
            "project_id": project_id,
            "nome": f"Projeto {project_id}",
            "email": email,
            "qtd_termos": qtd_termos,
        },
    )
    db.commit()


def _add_favorite(
    db: Session,
    *,
    row_id: int,
    project_id: int,
    parliamentarian_id: int,
) -> None:
    db.execute(
        text(
            """
            insert into projetos_parliamentarian
                (id, projeto_id, parliamentarian_id, created_at, updated_at)
            values
                (:row_id, :project_id, :parliamentarian_id, '2026-01-01', '2026-01-01')
            """
        ),
        {
            "row_id": row_id,
            "project_id": project_id,
            "parliamentarian_id": parliamentarian_id,
        },
    )
    db.commit()


def _favorite_count(db: Session, project_id: int, parliamentarian_id: int) -> int:
    return int(
        db.execute(
            text(
                """
                select count(*)
                from projetos_parliamentarian
                where projeto_id = :project_id
                  and parliamentarian_id = :parliamentarian_id
                """
            ),
            {
                "project_id": project_id,
                "parliamentarian_id": parliamentarian_id,
            },
        ).scalar_one()
    )


def _client_for_project(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    *,
    token_email: str = "assinante@example.com",
) -> TestClient:
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


# --- Contagem por casa ---------------------------------------------------


def test_favorite_counts_split_by_house() -> None:
    db = _make_session(qtd_termos=10, existing_favorites=[101, 202, 303])
    try:
        counts = projects._get_project_favorite_counts(db, 10)
        assert counts == {"camara": 2, "senado": 1}
    finally:
        db.close()


# --- Enforcement por casa ------------------------------------------------


def test_add_deputado_allowed_below_house_limit() -> None:
    db = _make_session(qtd_termos_camara=3, qtd_termos_senado=1, existing_favorites=[101])
    try:
        favorite = projects._create_project_favorite(db, 10, 202)
        assert favorite.parliamentarian_id == 202
        assert projects._get_project_favorite_counts(db, 10)["camara"] == 2
    finally:
        db.close()


def test_add_deputado_rejected_at_house_limit_with_house_message() -> None:
    db = _make_session(qtd_termos_camara=1, qtd_termos_senado=5, existing_favorites=[101])
    try:
        with pytest.raises(HTTPException) as excinfo:
            projects._create_project_favorite(db, 10, 202)
        assert excinfo.value.status_code == 403
        assert "Limite de deputados monitorados atingido" in str(excinfo.value.detail)
        assert projects._get_project_favorite_counts(db, 10)["camara"] == 1
    finally:
        db.close()


def test_add_senador_not_blocked_when_camara_full() -> None:
    db = _make_session(qtd_termos_camara=1, qtd_termos_senado=2, existing_favorites=[101])
    try:
        favorite = projects._create_project_favorite(db, 10, 303)
        assert favorite.parliamentarian_id == 303
        assert projects._get_project_favorite_counts(db, 10) == {"camara": 1, "senado": 1}
    finally:
        db.close()


def test_add_senador_rejected_at_senado_limit_with_house_message() -> None:
    db = _make_session(qtd_termos_camara=5, qtd_termos_senado=1, existing_favorites=[303])
    try:
        with pytest.raises(HTTPException) as excinfo:
            projects._create_project_favorite(db, 10, 404)
        assert excinfo.value.status_code == 403
        assert "Limite de senadores monitorados atingido" in str(excinfo.value.detail)
    finally:
        db.close()


def test_duplicate_conflict_takes_precedence_over_limit() -> None:
    db = _make_session(qtd_termos_camara=1, qtd_termos_senado=1, existing_favorites=[101])
    try:
        with pytest.raises(HTTPException) as excinfo:
            projects._create_project_favorite(db, 10, 101)
        assert excinfo.value.status_code == 409
        assert excinfo.value.detail == "Parlamentar já está favoritado neste projeto."
    finally:
        db.close()


# --- Quota por casa ------------------------------------------------------


def test_quota_reports_per_house_used_and_remaining() -> None:
    db = _make_session(
        qtd_termos_camara=3,
        qtd_termos_senado=2,
        existing_favorites=[101, 202, 303],
    )
    try:
        project = projects._ensure_active_project(db, 10)
        quota = projects._build_project_favorite_quota(db, project)

        assert quota.camara.limit == 3
        assert quota.camara.used == 2
        assert quota.camara.remaining == 1
        assert quota.senado.limit == 2
        assert quota.senado.used == 1
        assert quota.senado.remaining == 1
        # Totais derivados (soma das casas) preservam o contrato antigo.
        assert quota.limit == 5
        assert quota.used == 3
    finally:
        db.close()


def test_quota_uses_env_per_house_limit_by_tier_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "MAMUTE_TIER_LIMITS_JSON",
        '{"default-product":{"qtd_termos_camara":1,"qtd_termos_senado":5}}',
    )
    db = _make_session(qtd_termos=99, existing_favorites=[101])
    try:
        project = projects._ensure_active_project(db, 10)
        quota = projects._build_project_favorite_quota(db, project)

        assert quota.camara.limit == 1
        assert quota.senado.limit == 5
        assert quota.camara.used == 1
    finally:
        db.close()


def test_legacy_global_limit_applies_to_each_house() -> None:
    # Tier sem chaves por casa: o total global vira o limite de CADA casa
    # (regra de seed sem regressão), então o efetivo é herdado por casa.
    db = _make_session(qtd_termos=2, existing_favorites=[101])
    try:
        project = projects._ensure_active_project(db, 10)
        quota = projects._build_project_favorite_quota(db, project)

        assert quota.camara.limit == 2
        assert quota.senado.limit == 2
        assert quota.camara.used == 1
        assert quota.senado.used == 0
    finally:
        db.close()


# --- Isolamento de projeto (rotas legadas) -------------------------------


def test_legacy_project_favorites_list_rejects_other_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _make_session(qtd_termos=3, existing_favorites=[101])
    try:
        _add_project(db, project_id=20, email="victim@example.com")
        _add_favorite(db, row_id=20, project_id=20, parliamentarian_id=202)
        client = _client_for_project(monkeypatch, db)

        response = client.get("/api/projects/20/favorites")

        assert response.status_code == 404
    finally:
        db.close()


def test_legacy_project_favorites_add_rejects_other_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _make_session(qtd_termos=3, existing_favorites=[101])
    try:
        _add_project(db, project_id=20, email="victim@example.com")
        client = _client_for_project(monkeypatch, db)

        response = client.post(
            "/api/projects/20/favorites",
            json={"parliamentarian_id": 202},
        )

        assert response.status_code == 404
        assert _favorite_count(db, 20, 202) == 0
    finally:
        db.close()


def test_legacy_project_favorites_delete_rejects_other_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _make_session(qtd_termos=3, existing_favorites=[101])
    try:
        _add_project(db, project_id=20, email="victim@example.com")
        _add_favorite(db, row_id=20, project_id=20, parliamentarian_id=202)
        client = _client_for_project(monkeypatch, db)

        response = client.delete("/api/projects/20/favorites/202")

        assert response.status_code == 404
        assert _favorite_count(db, 20, 202) == 1
    finally:
        db.close()


def test_legacy_project_favorites_still_allow_owner_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _make_session(qtd_termos=3, existing_favorites=[101])
    try:
        client = _client_for_project(monkeypatch, db)

        list_response = client.get("/api/projects/10/favorites")
        assert list_response.status_code == 200
        assert [item["parliamentarian_id"] for item in list_response.json()] == [101]

        add_response = client.post(
            "/api/projects/10/favorites",
            json={"parliamentarian_id": 202},
        )
        assert add_response.status_code == 201
        assert _favorite_count(db, 10, 202) == 1

        delete_response = client.delete("/api/projects/10/favorites/202")
        assert delete_response.status_code == 204
        assert _favorite_count(db, 10, 202) == 0
    finally:
        db.close()
