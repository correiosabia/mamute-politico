"""Testes do endpoint que recebe webhooks member.* do Ghost."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient


SECRET = "test-webhook-secret"


def _body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _signature(raw_body: bytes, secret: str = SECRET, timestamp: int = 1_700_000_000_000) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        raw_body + str(timestamp).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}, t={timestamp}"


def _install_db_override(app: Any, dependency: Any) -> None:
    def override_db() -> Iterator[object]:
        yield object()

    app.dependency_overrides[dependency] = override_db


def test_receive_member_current_payload_syncs_project(monkeypatch: Any) -> None:
    from api.main import app
    from api.routers import ghost_webhooks
    from api.services.ghost_member_sync import GhostMemberProjectSyncResult

    monkeypatch.setenv("GHOST_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("GHOST_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS", "0")
    _install_db_override(app, ghost_webhooks.get_db)

    calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def fake_sync(db: object, current: dict[str, Any], previous: dict[str, Any]) -> GhostMemberProjectSyncResult:
        calls.append((current, previous))
        return GhostMemberProjectSyncResult(
            action="created",
            email=current["email"],
            project_id=42,
            product_id="free",
        )

    monkeypatch.setattr(ghost_webhooks, "sync_member_project", fake_sync)

    payload = {
        "member": {
            "current": {
                "email": "assinante@example.com",
                "name": "Assinante",
                "status": "free",
            },
            "previous": {},
        }
    }
    raw_body = _body(payload)

    response = TestClient(app).post(
        "/api/webhooks/ghost/members",
        content=raw_body,
        headers={"X-Ghost-Signature": _signature(raw_body)},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "action": "created",
        "email": "assinante@example.com",
        "project_id": 42,
        "product_id": "free",
        "reason": None,
    }
    assert calls == [(payload["member"]["current"], {})]


def test_receive_member_deleted_payload_soft_deletes_project(monkeypatch: Any) -> None:
    from api.main import app
    from api.routers import ghost_webhooks
    from api.services.ghost_member_sync import GhostMemberProjectSyncResult

    monkeypatch.setenv("GHOST_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("GHOST_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS", "0")
    _install_db_override(app, ghost_webhooks.get_db)

    calls: list[dict[str, Any]] = []

    def fake_soft_delete(db: object, previous: dict[str, Any]) -> GhostMemberProjectSyncResult:
        calls.append(previous)
        return GhostMemberProjectSyncResult(
            action="soft_deleted",
            email=previous["email"],
            project_id=43,
        )

    monkeypatch.setattr(ghost_webhooks, "soft_delete_member_project", fake_soft_delete)

    payload = {
        "member": {
            "current": {},
            "previous": {
                "email": "removido@example.com",
                "name": "Removido",
            },
        }
    }
    raw_body = _body(payload)

    response = TestClient(app).post(
        "/api/webhooks/ghost/members",
        content=raw_body,
        headers={"X-Ghost-Signature": _signature(raw_body)},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["action"] == "soft_deleted"
    assert response.json()["email"] == "removido@example.com"
    assert calls == [payload["member"]["previous"]]


def test_receive_member_webhook_rejects_invalid_signature(monkeypatch: Any) -> None:
    from api.main import app
    from api.routers import ghost_webhooks

    monkeypatch.setenv("GHOST_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("GHOST_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS", "0")
    _install_db_override(app, ghost_webhooks.get_db)

    raw_body = _body({"member": {"current": {"email": "x@example.com"}, "previous": {}}})

    response = TestClient(app).post(
        "/api/webhooks/ghost/members",
        content=raw_body,
        headers={"X-Ghost-Signature": _signature(raw_body, secret="wrong-secret")},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["detail"] == "Assinatura inválida."


def test_receive_member_webhook_requires_configured_secret(monkeypatch: Any) -> None:
    from api.main import app
    from api.routers import ghost_webhooks

    monkeypatch.delenv("GHOST_WEBHOOK_SECRET", raising=False)
    _install_db_override(app, ghost_webhooks.get_db)

    raw_body = _body({"member": {"current": {"email": "x@example.com"}, "previous": {}}})

    response = TestClient(app).post(
        "/api/webhooks/ghost/members",
        content=raw_body,
        headers={"X-Ghost-Signature": _signature(raw_body)},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 503


def test_sync_member_project_soft_deletes_previous_email_when_new_project_exists(
    monkeypatch: Any,
) -> None:
    from api.services import ghost_member_sync

    tier = SimpleNamespace(id=10, qtd_termos=5)
    new_project = SimpleNamespace(id=2, email="novo@example.com", deleted_at=None)
    previous_project = SimpleNamespace(id=1, email="antigo@example.com", deleted_at=None)

    def fake_get_project_by_email(session: object, email: str) -> Any:
        return {
            "novo@example.com": new_project,
            "antigo@example.com": previous_project,
        }.get(email)

    class FakeSession:
        def commit(self) -> None:
            pass

        def refresh(self, value: object) -> None:
            pass

    monkeypatch.setattr(ghost_member_sync, "_get_tier_by_product_id", lambda session, product_id: tier)
    monkeypatch.setattr(ghost_member_sync, "_get_project_by_email", fake_get_project_by_email)

    result = ghost_member_sync.sync_member_project(
        FakeSession(),
        {
            "email": "novo@example.com",
            "status": "free",
            "labels": [{"slug": "cliente"}],
        },
        {"email": "antigo@example.com"},
    )

    assert result.action == "updated"
    assert result.project_id == 2
    assert new_project.email == "novo@example.com"
    assert new_project.qtd_termos == 5
    assert new_project.tag_ghost == "cliente"
    assert previous_project.deleted_at is not None
