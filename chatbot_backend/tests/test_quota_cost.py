"""Gravação de tokens + cálculo de custo no mark_chat_usage."""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from chatbot_backend.app.services.quota import compute_cost_usd, mark_chat_usage


def test_compute_cost_usd() -> None:
    # 1M prompt @ 0.30 + 1M completion @ 2.50 = 2.80
    assert compute_cost_usd(1_000_000, 1_000_000, 0.30, 2.50) == 2.80
    # sem tokens => None
    assert compute_cost_usd(0, 0, 0.30, 2.50) is None
    assert compute_cost_usd(None, None, 0.30, 2.50) is None


def _session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            create table chatbot_usage (
                id integer primary key, projeto_id integer, email text,
                request_id text, period_start date, status text,
                question_chars integer default 0, answer_chars integer default 0,
                model text, prompt_tokens integer, completion_tokens integer,
                cost_usd numeric, created_at datetime, updated_at datetime
            )
            """
        )
        conn.exec_driver_sql(
            """
            create table model_pricing (
                id integer primary key, model text, input_usd_per_1m numeric,
                output_usd_per_1m numeric, currency text, source text, updated_at datetime
            )
            """
        )
        conn.exec_driver_sql(
            "insert into model_pricing (model, input_usd_per_1m, output_usd_per_1m) "
            "values ('gemini-2.5-flash', 0.30, 2.50)"
        )
        conn.exec_driver_sql(
            "insert into chatbot_usage (id, status, model) values (1, 'started', 'gemini-2.5-flash')"
        )
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_mark_usage_writes_tokens_and_cost() -> None:
    session = _session()
    mark_chat_usage(
        session, 1, status_value="completed", answer_chars=10,
        prompt_tokens=1_000_000, completion_tokens=1_000_000,
    )
    row = session.execute(
        text("select status, prompt_tokens, completion_tokens, cost_usd from chatbot_usage where id=1")
    ).first()
    assert row[0] == "completed"
    assert row[1] == 1_000_000
    assert row[2] == 1_000_000
    assert float(row[3]) == 2.80
    session.close()


def test_mark_usage_without_pricing_still_stores_tokens() -> None:
    session = _session()
    session.execute(text("delete from model_pricing"))
    session.commit()
    mark_chat_usage(
        session, 1, status_value="completed", answer_chars=10,
        prompt_tokens=500, completion_tokens=200,
    )
    row = session.execute(
        text("select prompt_tokens, completion_tokens, cost_usd from chatbot_usage where id=1")
    ).first()
    assert row[0] == 500
    assert row[1] == 200
    assert row[2] is None  # sem preço => custo fica nulo, mas tokens gravam
    session.close()
