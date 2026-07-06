"""Métricas admin: agregações de uso, custo e margem por usuário."""
from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api import main
from api.dependencies import get_db
from api.security import require_ghost_admin
from api.services.admin_metrics import get_usd_brl_rate, metrics_overview, metrics_users

PERIOD = date(2026, 7, 1)
RATE = 5.0  # câmbio fixo nos testes


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """create table tiers (id integer primary key, tier_name_debug text,
               product_id text, detalhes text not null, created_at datetime,
               updated_at datetime, deleted_at datetime)"""
        )
        conn.exec_driver_sql(
            """create table projetos (id integer primary key, nome text not null,
               cliente text, email text not null, tier_id integer, tag_ghost text,
               qtd_termos integer default 0, created_at datetime, updated_at datetime,
               deleted_at datetime)"""
        )
        conn.exec_driver_sql(
            """create table parliamentarian (id integer primary key, name text)"""
        )
        conn.exec_driver_sql(
            """create table projetos_parliamentarian (id integer primary key,
               projeto_id integer, parliamentarian_id integer, created_at datetime,
               updated_at datetime, deleted_at datetime)"""
        )
        conn.exec_driver_sql(
            """create table chatbot_usage (id integer primary key, projeto_id integer,
               email text, request_id text, period_start date, status text,
               question_chars integer default 0, answer_chars integer default 0,
               model text, prompt_tokens integer, completion_tokens integer,
               cost_usd numeric, created_at datetime, updated_at datetime)"""
        )
        conn.exec_driver_sql(
            "insert into tiers (id, tier_name_debug, product_id, detalhes) values "
            "(1, 'Cidadão', 'cidadao-mamute', :d)",
            {"d": json.dumps({"preco_mensal": 50, "qtd_consultas_ia_mes": 100, "qtd_termos": 10})},
        )
        conn.exec_driver_sql(
            "insert into projetos (id, nome, email, tier_id) values (1, 'Ana', 'ana@x.com', 1)"
        )
        # 2 consultas completed no período, com tokens e custo
        for i, cost in enumerate([0.10, 0.05]):
            conn.exec_driver_sql(
                "insert into chatbot_usage (projeto_id, email, request_id, period_start, "
                "status, prompt_tokens, completion_tokens, cost_usd) values "
                "(1, 'ana@x.com', :rid, '2026-07-01', 'completed', 100, 200, :c)",
                {"rid": f"r{i}", "c": cost},
            )
        # 1 favorito
        conn.exec_driver_sql(
            "insert into projetos_parliamentarian (projeto_id, parliamentarian_id) values (1, 1)"
        )
    return sessionmaker(bind=engine, expire_on_commit=False)()


@pytest.fixture()
def session() -> Session:
    return _make_session()


@pytest.fixture()
def client(session: Session) -> TestClient:
    main.app.dependency_overrides[get_db] = lambda: (yield session)
    main.app.dependency_overrides[require_ghost_admin] = lambda: "admin@x.com"
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()
    session.close()


def test_metrics_users(session: Session) -> None:
    users = metrics_users(session, PERIOD, RATE)
    assert len(users) == 1
    u = users[0]
    assert u["email"] == "ana@x.com"
    assert u["plano"] == "cidadao-mamute"
    assert u["preco_mensal"] == 50
    assert u["consultas_mes"] == 2
    assert u["tokens_mes"] == 600  # (100+200) * 2
    assert u["custo_mes"] == 0.15  # US$
    assert u["custo_mes_brl"] == 0.75  # 0.15 * 5.0
    assert u["margem_mes"] == 49.25  # 50 - 0.75 (R$)
    assert u["parlamentares_monitorados"] == 1
    assert u["acima_do_plano"] is False


def _session_limits(qtd_termos: int, favoritos: int, consultas: int, limite_ia: int) -> Session:
    """Sessão mínima p/ exercitar acima_do_plano com limites controlados."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """create table tiers (id integer primary key, tier_name_debug text,
               product_id text, detalhes text not null, created_at datetime,
               updated_at datetime, deleted_at datetime)"""
        )
        conn.exec_driver_sql(
            """create table projetos (id integer primary key, nome text not null,
               cliente text, email text not null, tier_id integer, tag_ghost text,
               qtd_termos integer default 0, created_at datetime, updated_at datetime,
               deleted_at datetime)"""
        )
        conn.exec_driver_sql("create table parliamentarian (id integer primary key, name text)")
        conn.exec_driver_sql(
            """create table projetos_parliamentarian (id integer primary key,
               projeto_id integer, parliamentarian_id integer, created_at datetime,
               updated_at datetime, deleted_at datetime)"""
        )
        conn.exec_driver_sql(
            """create table chatbot_usage (id integer primary key, projeto_id integer,
               email text, request_id text, period_start date, status text,
               question_chars integer default 0, answer_chars integer default 0,
               model text, prompt_tokens integer, completion_tokens integer,
               cost_usd numeric, created_at datetime, updated_at datetime)"""
        )
        conn.exec_driver_sql(
            "insert into tiers (id, tier_name_debug, product_id, detalhes) values (1,'T','p',:d)",
            {"d": json.dumps({"qtd_termos": qtd_termos, "qtd_consultas_ia_mes": limite_ia})},
        )
        conn.exec_driver_sql(
            "insert into projetos (id, nome, email, tier_id) values (1,'Ana','ana@x.com',1)"
        )
        for i in range(favoritos):
            conn.exec_driver_sql(
                "insert into projetos_parliamentarian (projeto_id, parliamentarian_id) values (1, :p)",
                {"p": i + 1},
            )
        for i in range(consultas):
            conn.exec_driver_sql(
                "insert into chatbot_usage (projeto_id, email, request_id, period_start, status) "
                "values (1,'ana@x.com',:r,'2026-07-01','completed')",
                {"r": f"r{i}"},
            )
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_acima_do_plano_por_parlamentares() -> None:
    # 2 favoritos, plano permite 1; sem consultas de IA → flag pelos parlamentares
    s = _session_limits(qtd_termos=1, favoritos=2, consultas=0, limite_ia=100)
    u = metrics_users(s, PERIOD, RATE)[0]
    assert u["parlamentares_monitorados"] == 2
    assert u["acima_do_plano"] is True
    assert metrics_overview(s, PERIOD, RATE)["usuarios_acima_do_plano"] == 1


def test_acima_do_plano_por_ia() -> None:
    # dentro do limite de parlamentares, mas estoura IA
    s = _session_limits(qtd_termos=10, favoritos=1, consultas=5, limite_ia=3)
    u = metrics_users(s, PERIOD, RATE)[0]
    assert u["acima_do_plano"] is True


def test_dentro_do_plano_nao_marca() -> None:
    s = _session_limits(qtd_termos=10, favoritos=2, consultas=2, limite_ia=100)
    assert metrics_users(s, PERIOD, RATE)[0]["acima_do_plano"] is False


def test_metrics_overview(session: Session) -> None:
    ov = metrics_overview(session, PERIOD, RATE)
    assert ov["usuarios"] == 1
    assert ov["consultas_mes"] == 2
    assert ov["custo_mes"] == 0.15
    assert ov["custo_mes_brl"] == 0.75
    assert ov["receita_mes"] == 50
    assert ov["margem_mes"] == 49.25
    assert ov["usd_brl_rate"] == 5.0


def test_get_usd_brl_rate_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAMUTE_USD_BRL_RATE", "5.42")
    assert get_usd_brl_rate() == 5.42


def _rate_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "create table usd_brl_rate (rate_date date primary key, bid numeric, "
            "fetched_at datetime)"
        )
        conn.exec_driver_sql(
            "insert into usd_brl_rate (rate_date, bid) values "
            "('2026-07-04', 6.10), ('2026-07-05', 6.25)"
        )
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_get_usd_brl_rate_from_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem env, a taxa vem da linha mais recente de usd_brl_rate (real do dia)."""
    from api.services import admin_metrics

    monkeypatch.delenv("MAMUTE_USD_BRL_RATE", raising=False)
    monkeypatch.setattr(admin_metrics, "_rate_cache", {"value": None, "at": 0.0})
    assert admin_metrics.get_usd_brl_rate(_rate_session()) == 6.25


def test_get_usd_brl_rate_no_db_uses_live_not_540(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem env e sem tabela: cai na busca ao vivo — nunca no antigo fixo 5.40."""
    from api.services import admin_metrics

    monkeypatch.delenv("MAMUTE_USD_BRL_RATE", raising=False)
    monkeypatch.setattr(admin_metrics, "_rate_cache", {"value": None, "at": 0.0})
    monkeypatch.setattr(admin_metrics, "_fetch_live_usd_brl", lambda: 5.73)
    assert admin_metrics.get_usd_brl_rate(None) == 5.73


def test_metrics_routes_admin_gated(client: TestClient) -> None:
    assert client.get("/api/admin/metrics/overview").status_code == 200
    body = client.get("/api/admin/metrics/users").json()
    assert body["users"][0]["email"] == "ana@x.com"
