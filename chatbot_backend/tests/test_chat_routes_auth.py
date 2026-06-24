from __future__ import annotations

from typing import Any, AsyncIterator

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from chatbot_backend.app.core.config import get_settings
from chatbot_backend.app.main import create_app
from chatbot_backend.app.routers import chat


class StubChatbotService:
    def __init__(self) -> None:
        self.invoke_calls = 0
        self.stream_calls = 0
        self.last_inputs: dict[str, Any] | None = None

    async def invoke(
        self,
        inputs: dict[str, Any],
        request_id: str | None = None,
    ) -> str:
        self.invoke_calls += 1
        self.last_inputs = inputs
        return "resposta autenticada"

    async def stream_response(
        self,
        inputs: dict[str, Any],
        request_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        self.stream_calls += 1
        yield {"type": "token", "value": "ok"}
        yield {"type": "end"}


@pytest.fixture
def chatbot_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, StubChatbotService]:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("PGVECTOR_CONNECTION", "sqlite:///:memory:")
    monkeypatch.setenv("MAMUTE_CHATBOT_QUOTA_ENABLED", "false")
    get_settings.cache_clear()

    service = StubChatbotService()
    monkeypatch.setattr(chat, "service", service)

    def fake_verify_token_header(authorization: str | None) -> dict[str, str]:
        if authorization != "Bearer valid-token":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cabeçalho Authorization ausente.",
            )
        return {"sub": "assinante@example.com"}

    monkeypatch.setattr(chat, "verify_token_header", fake_verify_token_header)
    return TestClient(create_app()), service


@pytest.mark.parametrize(
    ("path", "service_call_attr"),
    [
        ("/chat/chatbot/query", "invoke_calls"),
        ("/chat/chatbot/stream", "stream_calls"),
    ],
)
def test_chatbot_model_routes_require_token_when_quota_is_disabled(
    chatbot_client: tuple[TestClient, StubChatbotService],
    path: str,
    service_call_attr: str,
) -> None:
    client, service = chatbot_client

    response = client.post(path, json={"question": "Como foi a sessão?"})

    assert response.status_code == 401
    assert getattr(service, service_call_attr) == 0


def test_chatbot_query_accepts_valid_token_when_quota_is_disabled(
    chatbot_client: tuple[TestClient, StubChatbotService],
) -> None:
    client, service = chatbot_client

    response = client.post(
        "/chat/chatbot/query",
        headers={"Authorization": "Bearer valid-token"},
        json={"question": "Como foi a sessão?"},
    )

    assert response.status_code == 200
    assert response.json() == {"answer": "resposta autenticada"}
    assert service.invoke_calls == 1


def test_chatbot_query_accepts_bounded_history_when_quota_is_disabled(
    chatbot_client: tuple[TestClient, StubChatbotService],
) -> None:
    client, service = chatbot_client

    response = client.post(
        "/chat/chatbot/query",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "question": "Como foi a sessão?",
            "history": [
                {"role": "user", "content": "Oi"},
                {"role": "assistant", "content": "Olá, como posso ajudar?"},
            ],
        },
    )

    assert response.status_code == 200
    assert service.invoke_calls == 1
    assert service.last_inputs is not None
    assert len(service.last_inputs["history"]) == 2


@pytest.mark.parametrize(
    ("path", "service_call_attr"),
    [
        ("/chat/chatbot/query", "invoke_calls"),
        ("/chat/chatbot/stream", "stream_calls"),
    ],
)
def test_chatbot_model_routes_reject_overlong_question_before_service(
    chatbot_client: tuple[TestClient, StubChatbotService],
    path: str,
    service_call_attr: str,
) -> None:
    client, service = chatbot_client

    response = client.post(
        path,
        headers={"Authorization": "Bearer valid-token"},
        json={"question": "x" * 2001},
    )

    assert response.status_code == 422
    assert getattr(service, service_call_attr) == 0


def test_chatbot_query_rejects_too_many_history_messages_before_service(
    chatbot_client: tuple[TestClient, StubChatbotService],
) -> None:
    client, service = chatbot_client

    response = client.post(
        "/chat/chatbot/query",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "question": "Como foi a sessão?",
            "history": [
                {"role": "user", "content": f"mensagem {index}"}
                for index in range(21)
            ],
        },
    )

    assert response.status_code == 422
    assert service.invoke_calls == 0


def test_chatbot_query_rejects_large_total_context_before_service(
    chatbot_client: tuple[TestClient, StubChatbotService],
) -> None:
    client, service = chatbot_client

    response = client.post(
        "/chat/chatbot/query",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "question": "q" * 1000,
            "history": [
                {"role": "user", "content": "h" * 1900},
                {"role": "assistant", "content": "h" * 1900},
                {"role": "user", "content": "h" * 1900},
                {"role": "assistant", "content": "h" * 1900},
            ],
        },
    )

    assert response.status_code == 422
    assert service.invoke_calls == 0
