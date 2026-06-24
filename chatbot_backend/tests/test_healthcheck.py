from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from chatbot_backend.app import main as chatbot_main
from chatbot_backend.app.core.config import get_settings


class StubConnection:
    def __enter__(self) -> "StubConnection":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, statement: Any) -> None:
        return None


class HealthyEngine:
    def connect(self) -> StubConnection:
        return StubConnection()


class FailingEngine:
    def connect(self) -> StubConnection:
        raise SQLAlchemyError(
            "could not connect to postgresql://mamute:secret-password@db.internal/mamute"
        )


def _client_with_settings(monkeypatch) -> TestClient:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("PGVECTOR_CONNECTION", "sqlite:///:memory:")
    get_settings.cache_clear()
    return TestClient(chatbot_main.create_app())


def test_healthcheck_success_reports_database_status(monkeypatch) -> None:
    monkeypatch.setattr(chatbot_main, "engine", HealthyEngine())
    monkeypatch.setattr(
        chatbot_main,
        "create_engine",
        lambda *args, **kwargs: HealthyEngine(),
    )
    client = _client_with_settings(monkeypatch)

    response = client.get("/chat/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "environment": "test",
        "databases": {"mamute_db": "ok", "vector_db": "ok"},
    }


def test_healthcheck_failure_does_not_return_raw_database_exception(monkeypatch) -> None:
    monkeypatch.setattr(chatbot_main, "engine", FailingEngine())
    client = _client_with_settings(monkeypatch)

    response = client.get("/chat/health")

    assert response.status_code == 503
    body = response.json()
    assert body["detail"] == {
        "status": "error",
        "environment": "test",
        "databases": {"mamute_db": "error", "vector_db": "error"},
        "reason": "Falha ao verificar conectividade dos bancos.",
    }
    assert "secret-password" not in response.text
    assert "postgresql://" not in response.text
