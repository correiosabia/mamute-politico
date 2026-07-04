from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from chatbot_backend.app.core.config import get_settings
from chatbot_backend.app.services import quota


def _configure_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    enabled: bool = True,
    limits_json: str = "",
    tier_limits_json: str = "",
    default_limit: int = 0,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("PGVECTOR_CONNECTION", "sqlite:///:memory:")
    monkeypatch.setenv("MAMUTE_CHATBOT_QUOTA_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("MAMUTE_CHATBOT_DEFAULT_MONTHLY_LIMIT", str(default_limit))
    monkeypatch.setenv("MAMUTE_CHATBOT_MONTHLY_LIMITS_JSON", limits_json)
    monkeypatch.setenv("MAMUTE_TIER_LIMITS_JSON", tier_limits_json)
    get_settings.cache_clear()


def _make_session(
    *,
    tier_slug: str = "default-product",
    product_id: str = "target-tier-id",
    tier_details: dict | None = None,
    existing_statuses: list[str] | None = None,
) -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    period_start = quota.current_period_start()
    details = tier_details or {"ghost": {"slug": tier_slug}}
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            create table tiers (
                id integer primary key,
                product_id text not null,
                detalhes text not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            create table projetos (
                id integer primary key,
                email text not null,
                cliente text,
                tier_id integer,
                deleted_at datetime
            )
            """
        )
        conn.exec_driver_sql(
            """
            create table chatbot_usage (
                id integer primary key autoincrement,
                projeto_id integer not null,
                email text not null,
                request_id text not null unique,
                period_start date not null,
                status text not null,
                question_chars integer not null default 0,
                answer_chars integer not null default 0,
                model text,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp
            )
            """
        )
        conn.execute(
            text("insert into tiers (id, product_id, detalhes) values (1, :product_id, :details)"),
            {"product_id": product_id, "details": json.dumps(details)},
        )
        conn.exec_driver_sql(
            """
            insert into projetos (id, email, cliente, tier_id)
            values (10, 'assinante@example.com', 'target-tier-id', 1)
            """
        )
        for index, status in enumerate(existing_statuses or [], start=1):
            conn.execute(
                text(
                    """
                    insert into chatbot_usage
                        (
                            projeto_id,
                            email,
                            request_id,
                            period_start,
                            status,
                            question_chars,
                            answer_chars,
                            model
                        )
                    values
                        (10, 'assinante@example.com', :request_id, :period_start, :status, 12, 34, 'gpt-test')
                    """
                ),
                {
                    "request_id": f"existing-{index}",
                    "period_start": period_start,
                    "status": status,
                },
            )
    return Session(engine)


def test_quota_uses_env_limit_by_ghost_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_settings(
        monkeypatch,
        limits_json='{"default-product": 7}',
        default_limit=1,
    )
    # DB sem qtd_consultas_ia_mes → env (slug) é o fallback vigente.
    session = _make_session(tier_details={"ghost": {"slug": "default-product"}})
    try:
        current = quota.get_chat_quota(session, "assinante@example.com")

        assert current.enabled is True
        assert current.limit == 7
        assert current.used == 0
        assert current.remaining == 7
    finally:
        session.close()


def test_quota_falls_back_to_tier_details(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_settings(monkeypatch, default_limit=1)
    session = _make_session(tier_details={"ghost": {"slug": "default-product"}, "qtd_consultas_ia_mes": 3})
    try:
        current = quota.get_chat_quota(session, "assinante@example.com")

        assert current.limit == 3
    finally:
        session.close()


def test_quota_uses_generic_tier_limit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_settings(
        monkeypatch,
        tier_limits_json='{"default-product": {"qtd_consultas_ia_mes": 9}}',
        default_limit=1,
    )
    # DB sem qtd_consultas_ia_mes → MAMUTE_TIER_LIMITS_JSON (env) é o fallback vigente.
    session = _make_session(tier_details={"ghost": {"slug": "default-product"}})
    try:
        current = quota.get_chat_quota(session, "assinante@example.com")

        assert current.limit == 9
    finally:
        session.close()


def test_start_chat_usage_records_started_and_can_be_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_settings(monkeypatch, limits_json='{"default-product": 2}')
    session = _make_session()
    try:
        usage = quota.start_chat_usage(
            session,
            "assinante@example.com",
            request_id="req-1",
            question_chars=18,
            model="gpt-test",
        )
        assert usage.usage_id is not None
        assert usage.quota.used == 1
        assert usage.quota.remaining == 1

        quota.mark_chat_usage(
            session,
            usage.usage_id,
            status_value="completed",
            answer_chars=42,
        )
        row = session.execute(
            text("select status, question_chars, answer_chars, model from chatbot_usage where id = :id"),
            {"id": usage.usage_id},
        ).one()
        assert tuple(row) == ("completed", 18, 42, "gpt-test")
    finally:
        session.close()


def test_start_chat_usage_blocks_when_monthly_limit_is_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_settings(monkeypatch, limits_json='{"default-product": 1}')
    session = _make_session(existing_statuses=["completed"])
    try:
        with pytest.raises(HTTPException) as excinfo:
            quota.start_chat_usage(
                session,
                "assinante@example.com",
                request_id="req-2",
                question_chars=18,
                model="gpt-test",
            )

        assert excinfo.value.status_code == 403
        assert "Limite mensal de consultas IA atingido" in str(excinfo.value.detail)
        usage_count = session.execute(text("select count(*) from chatbot_usage")).scalar_one()
        assert usage_count == 1
    finally:
        session.close()


def test_quota_can_be_disabled_without_touching_usage_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_settings(monkeypatch, enabled=False)
    engine = create_engine("sqlite:///:memory:")
    session = Session(engine)
    try:
        current = quota.get_chat_quota(session, "assinante@example.com")

        assert current.enabled is False
        assert current.limit is None
        assert current.remaining is None
    finally:
        session.close()
