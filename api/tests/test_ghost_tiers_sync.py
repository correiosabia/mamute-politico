"""Espelho do catálogo de planos do Ghost na tabela `tiers` (CS-28).

Cobre as quatro regras: criar herdando, arquivar respeitando assinante,
reativar e marcar órfão — mais os endpoints admin de sync e desarquivamento.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api import main
from api.db.models.project import Tiers
from api.dependencies import get_db
from api.routers import admin as admin_router
from api.security import require_ghost_admin
from api.services import ghost_tiers_sync as svc


def _make_session(tiers: list[dict[str, Any]], projetos: int = 0) -> Session:
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
        for row in tiers:
            conn.exec_driver_sql(
                "insert into tiers (id, tier_name_debug, product_id, detalhes, deleted_at) "
                "values (:id, :nome, :pid, :det, :del)",
                {
                    "id": row["id"],
                    "nome": row["nome"],
                    "pid": row["product_id"],
                    "det": json.dumps(row.get("detalhes", {})),
                    "del": row.get("deleted_at"),
                },
            )
        for i in range(projetos):
            conn.exec_driver_sql(
                "insert into projetos (id, nome, email, tier_id) values (:id, :n, :e, :t)",
                {
                    "id": i + 1,
                    "n": f"bot-{i}",
                    "e": f"m{i}@x.com",
                    "t": tiers[0]["id"],
                },
            )
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def _ghost(
    product_id: str,
    *,
    name: str,
    price: float = 0.0,
    active: bool = True,
    slug: str | None = None,
    tier_id: str | None = None,
    tipo: str = "paid",
) -> dict[str, Any]:
    return {
        "product_id": product_id,
        "ghost_tier_id": tier_id or product_id,
        "slug": slug or product_id,
        "type": tipo,
        "name": name,
        "monthly_price": price,
        "active": active,
    }


def _tier(session: Session, product_id: str) -> Tiers:
    return session.execute(
        select(Tiers).where(Tiers.product_id == product_id)
    ).scalars().one()


# --- normalização ---------------------------------------------------------


def test_normalize_reads_active_and_maps_free_by_slug() -> None:
    parsed = {
        t["product_id"]: t
        for t in svc.normalize_ghost_tiers(
            [
                {
                    "id": "gh_free",
                    "name": "Elefante Livre",
                    "slug": "free",
                    "type": "free",
                    "monthly_price": None,
                    "active": True,
                },
                {
                    "id": "gh_paid",
                    "name": "Mamute Completo",
                    "slug": "cidadao-mamute",
                    "type": "paid",
                    "monthly_price": 5000,
                    "active": False,
                },
            ]
        )
    }
    assert parsed["free"]["monthly_price"] == 0.0
    assert parsed["free"]["active"] is True
    assert parsed["gh_paid"]["monthly_price"] == 50.0
    assert parsed["gh_paid"]["active"] is False


def test_normalize_treats_missing_active_as_true() -> None:
    parsed = svc.normalize_ghost_tiers([{"id": "x", "name": "X", "type": "paid"}])
    assert parsed[0]["active"] is True


# --- criação com herança --------------------------------------------------


def test_creates_missing_tier_inheriting_closest_cheaper_plan() -> None:
    session = _make_session(
        [
            {
                "id": 1,
                "nome": "Elefante Livre",
                "product_id": "free",
                "detalhes": {"qtd_termos": 1, "qtd_consultas_ia_mes": 10, "preco_mensal": 0.0},
            },
            {
                "id": 2,
                "nome": "Mamute Completo",
                "product_id": "gh_paid",
                "detalhes": {
                    "qtd_termos": 10,
                    "qtd_consultas_ia_mes": 100,
                    "periodicidade_email": ["fortnight"],
                    "preco_mensal": 50.0,
                },
            },
        ]
    )
    summary = svc.sync_tiers(
        session,
        [
            _ghost("free", name="Elefante Livre", tipo="free", slug="free"),
            _ghost("gh_paid", name="Mamute Completo", price=50.0),
            _ghost("gh_novo", name="Mamute Turbo", price=120.0),
        ],
    )

    assert [c["product_id"] for c in summary.created] == ["gh_novo"]
    novo = _tier(session, "gh_novo")
    # herda do plano ativo mais caro entre os que custam até o preço do novo
    assert novo.detalhes["qtd_termos"] == 10
    assert novo.detalhes["qtd_consultas_ia_mes"] == 100
    assert novo.detalhes["periodicidade_email"] == ["fortnight"]
    assert novo.detalhes["preco_mensal"] == 120.0
    assert novo.detalhes["ghost"]["pending_review"] is True
    assert novo.detalhes["ghost"]["herdado_de"] == "gh_paid"
    assert novo.deleted_at is None


def test_new_cheapest_tier_inherits_from_cheapest_existing() -> None:
    session = _make_session(
        [
            {
                "id": 1,
                "nome": "Mamute Completo",
                "product_id": "gh_paid",
                "detalhes": {"qtd_termos": 10, "preco_mensal": 50.0},
            }
        ]
    )
    svc.sync_tiers(
        session,
        [
            _ghost("gh_paid", name="Mamute Completo", price=50.0),
            _ghost("gh_mini", name="Mamute Mini", price=9.9),
        ],
    )
    assert _tier(session, "gh_mini").detalhes["qtd_termos"] == 10


def test_created_tier_already_archived_comes_soft_deleted() -> None:
    session = _make_session(
        [{"id": 1, "nome": "Free", "product_id": "free", "detalhes": {"qtd_termos": 1}}]
    )
    svc.sync_tiers(
        session,
        [
            _ghost("free", name="Free", tipo="free"),
            _ghost("gh_old", name="Plano Velho", price=30.0, active=False),
        ],
    )
    assert _tier(session, "gh_old").deleted_at is not None


# --- arquivamento ---------------------------------------------------------


def test_archived_without_subscribers_is_soft_deleted() -> None:
    session = _make_session(
        [
            {
                "id": 1,
                "nome": "Eleitor Elefante",
                "product_id": "gh_old",
                "detalhes": {"qtd_termos": 3, "preco_mensal": 50.0},
            }
        ]
    )
    summary = svc.sync_tiers(
        session, [_ghost("gh_old", name="Eleitor Elefante", price=50.0, active=False)]
    )

    tier = _tier(session, "gh_old")
    assert tier.deleted_at is not None
    assert tier.detalhes["ghost"]["active"] is False
    assert summary.archived[0]["assinantes"] == 0


def test_archived_with_subscribers_keeps_serving_them() -> None:
    session = _make_session(
        [
            {
                "id": 1,
                "nome": "Eleitor Elefante",
                "product_id": "gh_old",
                "detalhes": {"qtd_termos": 3, "preco_mensal": 50.0},
            }
        ],
        projetos=2,
    )
    summary = svc.sync_tiers(
        session, [_ghost("gh_old", name="Eleitor Elefante", price=50.0, active=False)]
    )

    tier = _tier(session, "gh_old")
    assert tier.deleted_at is None, "assinante ativo não pode perder o plano"
    assert tier.detalhes["ghost"]["active"] is False
    assert tier.detalhes["ghost"]["archived_with_subscribers"] is True
    assert summary.archived[0]["assinantes"] == 2


def test_reactivated_in_ghost_comes_back() -> None:
    session = _make_session(
        [
            {
                "id": 1,
                "nome": "Eleitor Elefante",
                "product_id": "gh_old",
                "detalhes": {
                    "qtd_termos": 3,
                    "ghost": {"active": False, "target_tier_id": "gh_old"},
                },
                "deleted_at": "2026-07-01 00:00:00",
            }
        ]
    )
    summary = svc.sync_tiers(
        session, [_ghost("gh_old", name="Eleitor Elefante", price=50.0, active=True)]
    )

    tier = _tier(session, "gh_old")
    assert tier.deleted_at is None
    assert tier.detalhes["ghost"]["active"] is True
    assert summary.reactivated == ["gh_old"]


# --- preservação e órfãos -------------------------------------------------


def test_sync_never_overwrites_entitlements() -> None:
    session = _make_session(
        [
            {
                "id": 1,
                "nome": "Nome Velho",
                "product_id": "gh_paid",
                "detalhes": {
                    "qtd_termos": 7,
                    "qtd_consultas_ia_mes": 42,
                    "preco_mensal": 10.0,
                },
            }
        ]
    )
    svc.sync_tiers(session, [_ghost("gh_paid", name="Nome Novo", price=99.0)])

    tier = _tier(session, "gh_paid")
    assert tier.tier_name_debug == "Nome Novo"
    assert tier.detalhes["preco_mensal"] == 99.0
    assert tier.detalhes["qtd_termos"] == 7
    assert tier.detalhes["qtd_consultas_ia_mes"] == 42


def test_local_tier_without_ghost_pair_is_flagged_orphan_not_deleted() -> None:
    session = _make_session(
        [
            {"id": 1, "nome": "Free", "product_id": "free", "detalhes": {"qtd_termos": 1}},
            {
                "id": 2,
                "nome": "Só local",
                "product_id": "gh_fantasma",
                "detalhes": {"qtd_termos": 5},
            },
        ]
    )
    summary = svc.sync_tiers(session, [_ghost("free", name="Free", tipo="free")])

    fantasma = _tier(session, "gh_fantasma")
    assert fantasma.deleted_at is None
    assert fantasma.detalhes["ghost"]["orphan"] is True
    assert summary.orphans == ["gh_fantasma"]


def test_sync_is_idempotent() -> None:
    session = _make_session(
        [{"id": 1, "nome": "Free", "product_id": "free", "detalhes": {"qtd_termos": 1}}]
    )
    ghost = [
        _ghost("free", name="Free", tipo="free"),
        _ghost("gh_novo", name="Novo", price=20.0),
    ]
    first = svc.sync_tiers(session, ghost)
    second = svc.sync_tiers(session, ghost)

    assert len(first.created) == 1
    assert second.created == []
    assert second.orphans == []
    assert len(session.execute(select(Tiers)).scalars().all()) == 2


# --- endpoints ------------------------------------------------------------


@pytest.fixture()
def admin_client() -> TestClient:
    session = _make_session(
        [
            {
                "id": 1,
                "nome": "Elefante Livre",
                "product_id": "free",
                "detalhes": {"qtd_termos": 1},
            },
            {
                "id": 2,
                "nome": "Eleitor Elefante",
                "product_id": "gh_old",
                "detalhes": {
                    "qtd_termos": 3,
                    "ghost": {"active": False, "target_tier_id": "gh_old"},
                },
                "deleted_at": "2026-07-01 00:00:00",
            },
        ]
    )

    def _override_get_db():
        yield session

    main.app.dependency_overrides[get_db] = _override_get_db
    main.app.dependency_overrides[require_ghost_admin] = lambda: "admin@x.com"
    client = TestClient(main.app)
    client.session = session  # type: ignore[attr-defined]
    yield client
    main.app.dependency_overrides.clear()
    session.close()


def test_list_hides_archived_by_default(admin_client: TestClient) -> None:
    data = admin_client.get("/api/admin/tiers").json()
    assert [t["product_id"] for t in data] == ["free"]


def test_list_include_archived_marks_status(admin_client: TestClient) -> None:
    data = admin_client.get("/api/admin/tiers", params={"include_archived": True}).json()
    por_id = {t["product_id"]: t for t in data}
    assert set(por_id) == {"free", "gh_old"}
    assert por_id["gh_old"]["arquivado"] is True
    assert por_id["gh_old"]["deleted_at"] is not None
    assert por_id["free"]["arquivado"] is False


def test_sync_endpoint_returns_summary(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_sync(session, *args, **kwargs):
        return svc.TierSyncSummary(created=[{"product_id": "gh_novo", "name": "Novo"}])

    monkeypatch.setattr(admin_router, "run_ghost_tiers_sync", fake_sync)
    resp = admin_client.post("/api/admin/tiers/sync")

    assert resp.status_code == 200
    assert resp.json()["created"][0]["product_id"] == "gh_novo"


def test_sync_endpoint_503_without_ghost_config(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session, *args, **kwargs):
        raise svc.GhostTiersSyncError("sem config")

    monkeypatch.setattr(admin_router, "run_ghost_tiers_sync", boom)
    assert admin_client.post("/api/admin/tiers/sync").status_code == 503


def test_unarchive_writes_to_ghost_and_restores_locally(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    chamadas: dict[str, Any] = {}

    monkeypatch.setattr(
        admin_router,
        "get_ghost_admin_settings",
        lambda: type("S", (), {"api_key": "k:ab", "admin_url": "https://g/api"})(),
    )
    monkeypatch.setattr(admin_router, "generate_admin_token", lambda key: "tok")

    def fake_set_active(admin_url, token, tier_id, active, *a, **kw):
        chamadas["tier_id"] = tier_id
        chamadas["active"] = active
        return {"id": tier_id, "active": active}

    monkeypatch.setattr(admin_router, "set_ghost_tier_active", fake_set_active)
    # o re-sync roda com o catálogo já reativado
    monkeypatch.setattr(
        admin_router,
        "run_ghost_tiers_sync",
        lambda session, *a, **kw: svc.sync_tiers(
            session,
            [
                _ghost("free", name="Elefante Livre", tipo="free"),
                _ghost("gh_old", name="Eleitor Elefante", price=50.0, active=True),
            ],
        ),
    )

    resp = admin_client.post("/api/admin/tiers/2/unarchive")

    assert resp.status_code == 200
    assert chamadas == {"tier_id": "gh_old", "active": True}
    body = resp.json()
    assert body["arquivado"] is False
    assert body["deleted_at"] is None


def test_unarchive_unknown_tier_404(admin_client: TestClient) -> None:
    assert admin_client.post("/api/admin/tiers/999/unarchive").status_code == 404


# --- rede de segurança no webhook de membro -------------------------------


def test_member_sync_pulls_catalog_when_tier_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assinatura de plano criado no Ghost depois do último sync."""
    from api.services import ghost_member_sync

    session = _make_session(
        [{"id": 1, "nome": "Free", "product_id": "free", "detalhes": {"qtd_termos": 1}}]
    )

    def fake_tier_sync(sess) -> bool:
        svc.sync_tiers(
            sess,
            [
                _ghost("free", name="Free", tipo="free"),
                _ghost("gh_novo", name="Plano Novo", price=30.0),
            ],
        )
        return True

    monkeypatch.setattr(ghost_member_sync, "_run_tier_sync", fake_tier_sync)

    result = ghost_member_sync.sync_member_project(
        session,
        {
            "email": "novo@x.com",
            "name": "Novo",
            "subscriptions": [{"tier": {"id": "gh_novo"}}],
        },
    )

    assert result.action == "created"
    assert result.product_id == "gh_novo"
    assert _tier(session, "gh_novo").tier_name_debug == "Plano Novo"


def test_member_sync_still_reports_missing_tier_when_ghost_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.services import ghost_member_sync

    session = _make_session(
        [{"id": 1, "nome": "Free", "product_id": "free", "detalhes": {"qtd_termos": 1}}]
    )
    monkeypatch.setattr(ghost_member_sync, "_run_tier_sync", lambda sess: False)

    result = ghost_member_sync.sync_member_project(
        session,
        {"email": "novo@x.com", "subscriptions": [{"tier": {"id": "gh_novo"}}]},
    )

    assert result.action == "ignored"
    assert result.reason == "missing_tier"
