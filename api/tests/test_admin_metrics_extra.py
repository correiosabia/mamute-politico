"""Ferramentas, parlamentares (casa/estado), IA e limite/busca de usuários."""
from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.services.admin_metrics import (
    metrics_ia,
    metrics_parliamentarians,
    metrics_sections,
    metrics_tools,
    metrics_users,
)

PERIOD = date(2026, 7, 1)
RATE = 5.0


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "create table tiers (id integer primary key, tier_name_debug text, product_id text, "
            "detalhes text not null, created_at datetime, updated_at datetime, deleted_at datetime)"
        )
        conn.exec_driver_sql(
            "create table projetos (id integer primary key, nome text, cliente text, email text, "
            "tier_id integer, tag_ghost text, qtd_termos integer default 0, created_at datetime, "
            "updated_at datetime, deleted_at datetime)"
        )
        conn.exec_driver_sql(
            "create table parliamentarian (id integer primary key, name text, type text, state_elected text)"
        )
        conn.exec_driver_sql(
            "create table projetos_parliamentarian (id integer primary key, projeto_id integer, "
            "parliamentarian_id integer, created_at datetime, updated_at datetime, deleted_at datetime)"
        )
        conn.exec_driver_sql(
            "create table chatbot_usage (id integer primary key, projeto_id integer, email text, "
            "request_id text, period_start date, status text, question_chars integer, answer_chars integer, "
            "model text, prompt_tokens integer, completion_tokens integer, cost_usd numeric, "
            "created_at datetime, updated_at datetime)"
        )
        conn.exec_driver_sql(
            "create table usage_events (id integer primary key, projeto_id integer, email text, "
            "event_type text not null, page text, section text, parliamentarian_id integer, created_at datetime)"
        )
        conn.exec_driver_sql(
            "insert into tiers (id, tier_name_debug, product_id, detalhes) values (1,'Cid','cidadao',:d)",
            {"d": json.dumps({"preco_mensal": 50})},
        )
        conn.exec_driver_sql(
            "insert into projetos (id, nome, email, tier_id) values "
            "(1,'Ana Souza','ana@x.com',1),(2,'Bruno Lima','bruno@x.com',1)"
        )
        conn.exec_driver_sql(
            "insert into parliamentarian (id, name, type, state_elected) values "
            "(1,'Dep SP','deputado','SP'),(2,'Sen RJ','senador','RJ'),(3,'Dep SP2','deputado','SP')"
        )
        # favoritos: parl 1 monitorado por 2 projetos, parl 2 por 1, parl 3 por 1
        conn.exec_driver_sql(
            "insert into projetos_parliamentarian (projeto_id, parliamentarian_id) values "
            "(1,1),(2,1),(1,2),(1,3)"
        )
        conn.exec_driver_sql(
            "insert into chatbot_usage (projeto_id, email, request_id, period_start, status, "
            "prompt_tokens, completion_tokens, cost_usd, created_at) values "
            "(1,'ana@x.com','r1','2026-07-01','completed',100,200,0.10,'2026-07-01'),"
            "(1,'ana@x.com','r2','2026-07-01','completed',100,200,0.05,'2026-07-02')"
        )
        conn.exec_driver_sql(
            "insert into usage_events (projeto_id, event_type, page) values "
            "(1,'page_view','dashboard'),(1,'page_view','dashboard'),(1,'page_view','pesquisa')"
        )
        conn.exec_driver_sql(
            "insert into usage_events (projeto_id, event_type, parliamentarian_id) values "
            "(1,'favorite_added',1),(1,'favorite_removed',1)"
        )
        conn.exec_driver_sql(
            "insert into usage_events (projeto_id, event_type, page, section) values "
            "(1,'section_view','parlamentar','taquigraficas'),"
            "(1,'section_view','parlamentar','taquigraficas'),"
            "(1,'section_view','parlamentar','temas-discurso')"
        )
    return sessionmaker(bind=engine, expire_on_commit=False)()


@pytest.fixture()
def session() -> Session:
    return _make_session()


def test_tools(session: Session) -> None:
    tools = {t["tool"]: t["uses"] for t in metrics_tools(session)}
    assert tools["Dashboard Geral"] == 2
    assert tools["Pesquisa IA (consultas)"] == 2  # 2 chatbot_usage completed
    assert tools["Monitoramento (trocas)"] == 2  # 1 added + 1 removed


def test_parliamentarians_by_house_and_state(session: Session) -> None:
    p = metrics_parliamentarians(session)
    # parl 1 (SP, camara) = 2 monitores é o top
    assert p["top"][0]["parliamentarian_id"] == 1
    assert p["top"][0]["monitors"] == 2
    assert p["by_house"] == {"camara": 3, "senado": 1}  # parl1(2)+parl3(1) camara, parl2(1) senado
    by_state = {s["state"]: s["monitors"] for s in p["by_state"]}
    assert by_state == {"SP": 3, "RJ": 1}


def test_ia(session: Session) -> None:
    ia = metrics_ia(session, PERIOD, RATE)
    assert ia["consultas_mes"] == 2
    assert ia["custo_mes_brl"] == 0.75  # 0.15 * 5
    assert len(ia["por_dia"]) == 2
    assert ia["top_usuarios"][0]["email"] == "ana@x.com"


def test_sections(session: Session) -> None:
    sections = metrics_sections(session)
    top = {(s["section"]): s["views"] for s in sections}
    assert top["taquigraficas"] == 2
    assert top["temas-discurso"] == 1
    # ordenado por views desc
    assert sections[0]["section"] == "taquigraficas"
    assert sections[0]["page"] == "Página de Parlamentar"


def test_users_limit_and_search(session: Session) -> None:
    assert len(metrics_users(session, PERIOD, RATE, limit=1)) == 1
    found = metrics_users(session, PERIOD, RATE, search="bruno")
    assert len(found) == 1 and found[0]["email"] == "bruno@x.com"
