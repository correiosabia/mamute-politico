"""Limite semanal de consultas IA, aplicado junto com o teto mensal."""
from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

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
    tier_limits_json: str = "",
    default_limit: int = 1,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("PGVECTOR_CONNECTION", "sqlite:///:memory:")
    monkeypatch.setenv("MAMUTE_CHATBOT_QUOTA_ENABLED", "true")
    monkeypatch.setenv("MAMUTE_CHATBOT_DEFAULT_MONTHLY_LIMIT", str(default_limit))
    monkeypatch.setenv("MAMUTE_CHATBOT_MONTHLY_LIMITS_JSON", "")
    monkeypatch.setenv("MAMUTE_TIER_LIMITS_JSON", tier_limits_json)
    get_settings.cache_clear()


def _make_session(
    *,
    tier_details: dict,
    existing_usages: list[dict] | None = None,
) -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    month = quota.current_period_start()
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "create table tiers (id integer primary key, product_id text not null, detalhes text not null)"
        )
        conn.exec_driver_sql(
            "create table projetos (id integer primary key, email text not null, cliente text, tier_id integer, deleted_at datetime)"
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
                prompt_tokens integer,
                completion_tokens integer,
                cost_usd numeric,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp
            )
            """
        )
        conn.execute(
            text("insert into tiers (id, product_id, detalhes) values (1, 'free', :d)"),
            {"d": json.dumps(tier_details)},
        )
        conn.exec_driver_sql(
            "insert into projetos (id, email, cliente, tier_id) values (10, 'assinante@example.com', 'free', 1)"
        )
        for index, usage in enumerate(existing_usages or [], start=1):
            conn.execute(
                text(
                    """
                    insert into chatbot_usage
                        (projeto_id, email, request_id, period_start, status, created_at)
                    values
                        (10, 'assinante@example.com', :rid, :period_start, :status, :created_at)
                    """
                ),
                {
                    "rid": f"u-{index}",
                    "period_start": usage.get("period_start", month),
                    "status": usage["status"],
                    "created_at": usage["created_at"],
                },
            )
    return Session(engine)


def _this_monday() -> date:
    return quota.current_week_start()


def test_current_week_start_returns_monday() -> None:
    wed = datetime(2026, 7, 22, 15, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    assert quota.current_week_start(wed) == date(2026, 7, 20)


def test_resolve_weekly_limit_from_tier_details(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_settings(monkeypatch)
    session = _make_session(tier_details={"ghost": {"slug": "free"}, "qtd_consultas_ia_semana": 2})
    try:
        project = quota._load_project(session, "assinante@example.com")
        assert quota.resolve_weekly_limit(project) == 2
    finally:
        session.close()


def test_resolve_weekly_limit_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_settings(monkeypatch)
    session = _make_session(tier_details={"ghost": {"slug": "free"}})
    try:
        project = quota._load_project(session, "assinante@example.com")
        assert quota.resolve_weekly_limit(project) is None
    finally:
        session.close()


def test_weekly_blocks_even_when_monthly_has_room(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_settings(
        monkeypatch,
        tier_limits_json='{"free":{"qtd_consultas_ia_mes":10,"qtd_consultas_ia_semana":2}}',
    )
    monday = _this_monday()
    session = _make_session(
        tier_details={"ghost": {"slug": "free"}},
        existing_usages=[
            {"status": "completed", "created_at": f"{monday} 09:00:00"},
            {"status": "completed", "created_at": f"{monday} 10:00:00"},
        ],
    )
    try:
        with pytest.raises(HTTPException) as excinfo:
            quota.start_chat_usage(
                session, "assinante@example.com", request_id="new", question_chars=5, model="m"
            )
        assert excinfo.value.status_code == 403
        assert "semanal" in str(excinfo.value.detail).lower()
    finally:
        session.close()


def test_weekly_ignores_previous_week_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_settings(
        monkeypatch,
        tier_limits_json='{"free":{"qtd_consultas_ia_mes":10,"qtd_consultas_ia_semana":2}}',
    )
    session = _make_session(
        tier_details={"ghost": {"slug": "free"}},
        existing_usages=[
            {"status": "completed", "created_at": "2000-01-03 09:00:00", "period_start": "2000-01-01"},
            {"status": "completed", "created_at": "2000-01-04 09:00:00", "period_start": "2000-01-01"},
        ],
    )
    try:
        usage = quota.start_chat_usage(
            session, "assinante@example.com", request_id="new", question_chars=5, model="m"
        )
        assert usage.usage_id is not None
    finally:
        session.close()


def test_get_quota_reports_both_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_settings(
        monkeypatch,
        tier_limits_json='{"free":{"qtd_consultas_ia_mes":10,"qtd_consultas_ia_semana":2}}',
    )
    monday = _this_monday()
    session = _make_session(
        tier_details={"ghost": {"slug": "free"}},
        existing_usages=[{"status": "completed", "created_at": f"{monday} 09:00:00"}],
    )
    try:
        q = quota.get_chat_quota(session, "assinante@example.com")
        assert q.weekly is not None and q.weekly.limit == 2 and q.weekly.used == 1
        assert q.monthly is not None and q.monthly.limit == 10 and q.monthly.used == 1
        # binding = semanal (menos folga / reset mais cedo)
        assert q.limit == 2
        assert q.remaining == 1
    finally:
        session.close()
