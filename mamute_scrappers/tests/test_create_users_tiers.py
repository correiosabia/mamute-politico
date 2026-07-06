from __future__ import annotations

import importlib
import sys
from typing import Any


ADMIN_KEY = "test:" + "a" * 64


def _load_create_users(monkeypatch: Any) -> Any:
    monkeypatch.setenv("GHOST_API", ADMIN_KEY)
    monkeypatch.setenv("GHOST_ADMIN_URL", "https://ghost.test/ghost/api/admin")
    sys.modules.pop("mamute_scrappers.scripts.create_users", None)
    return importlib.import_module("mamute_scrappers.scripts.create_users")


def test_resolve_product_id_prefers_tiers_over_free_status(monkeypatch: Any) -> None:
    create_users = _load_create_users(monkeypatch)

    assert (
        create_users._resolve_product_id(
            {
                "status": "free",
                "tiers": [{"id": "ghost-paid-tier-id"}],
            }
        )
        == "ghost-paid-tier-id"
    )


def test_resolve_product_id_keeps_free_without_paid_tier(monkeypatch: Any) -> None:
    create_users = _load_create_users(monkeypatch)

    assert create_users._resolve_product_id({"status": "free", "tiers": []}) == "free"


def test_request_ghost_members_includes_tiers_and_subscriptions(monkeypatch: Any) -> None:
    create_users = _load_create_users(monkeypatch)
    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200
        text = "{}"

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr(create_users.requests, "get", fake_get)

    create_users._request_ghost_members("token", page=2)

    assert "include=tiers,subscriptions" in captured["url"]
    assert "page=2" in captured["url"]
    assert captured["kwargs"]["headers"]["Authorization"] == "Ghost token"
