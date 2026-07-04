"""Testes do gate de admin (require_ghost_admin).

O gate deve devolver 404 para TUDO que nao seja admin autenticado com a
feature flag ligada — sem vazar a existencia da superficie /admin.
"""
from __future__ import annotations

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    from api.main import app

    return TestClient(app)


def _fake_decode(payload: dict):
    def _decode(_token: str) -> dict:
        return payload

    return _decode


def test_admin_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from api import security

    monkeypatch.setenv("MAMUTE_ADMIN_PANELS_ENABLED", "true")
    monkeypatch.setenv("MAMUTE_ADMIN_EMAILS", "admin@x.com, other@x.com")
    monkeypatch.setattr(security, "_decode_ghost_jwt", _fake_decode({"sub": "Admin@X.com"}))

    resp = client.get("/api/admin/whoami", headers={"Authorization": "Bearer faketoken"})

    assert resp.status_code == 200
    assert resp.json() == {"email": "admin@x.com", "is_admin": True}


def test_flag_off_is_404_even_for_admin(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from api import security

    monkeypatch.setenv("MAMUTE_ADMIN_PANELS_ENABLED", "false")
    monkeypatch.setenv("MAMUTE_ADMIN_EMAILS", "admin@x.com")
    monkeypatch.setattr(security, "_decode_ghost_jwt", _fake_decode({"sub": "admin@x.com"}))

    resp = client.get("/api/admin/whoami", headers={"Authorization": "Bearer faketoken"})

    assert resp.status_code == 404


def test_non_admin_email_is_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from api import security

    monkeypatch.setenv("MAMUTE_ADMIN_PANELS_ENABLED", "true")
    monkeypatch.setenv("MAMUTE_ADMIN_EMAILS", "admin@x.com")
    monkeypatch.setattr(security, "_decode_ghost_jwt", _fake_decode({"sub": "rando@x.com"}))

    resp = client.get("/api/admin/whoami", headers={"Authorization": "Bearer faketoken"})

    assert resp.status_code == 404


def test_no_token_is_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAMUTE_ADMIN_PANELS_ENABLED", "true")
    monkeypatch.setenv("MAMUTE_ADMIN_EMAILS", "admin@x.com")

    resp = client.get("/api/admin/whoami")

    assert resp.status_code == 404


def test_invalid_token_is_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from api import security

    def _boom(_token: str) -> dict:
        raise pyjwt.InvalidTokenError("bad")

    monkeypatch.setenv("MAMUTE_ADMIN_PANELS_ENABLED", "true")
    monkeypatch.setenv("MAMUTE_ADMIN_EMAILS", "admin@x.com")
    monkeypatch.setattr(security, "_decode_ghost_jwt", _boom)

    resp = client.get("/api/admin/whoami", headers={"Authorization": "Bearer faketoken"})

    assert resp.status_code == 404
