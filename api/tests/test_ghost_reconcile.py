"""Testes da reconciliação Ghost Admin API -> API local."""

from __future__ import annotations

from typing import Any


def test_run_ghost_reconciliation_skips_without_admin_config(monkeypatch: Any) -> None:
    from api.services import ghost_reconcile

    monkeypatch.setattr(ghost_reconcile, "get_ghost_admin_settings", lambda: None)

    result = ghost_reconcile.run_ghost_reconciliation(object())

    assert result.action == "skipped"
    assert result.reason == "missing_ghost_admin_config"


def test_run_ghost_reconciliation_syncs_tiers_before_members(monkeypatch: Any) -> None:
    from api.services import ghost_reconcile
    from api.services.ghost_admin import GhostAdminSettings

    calls: list[str] = []
    session = object()

    monkeypatch.setattr(
        ghost_reconcile,
        "get_ghost_admin_settings",
        lambda: GhostAdminSettings(api_key="kid:" + "ab" * 32, admin_url="https://ghost.test"),
    )
    monkeypatch.setattr(ghost_reconcile, "generate_admin_token", lambda api_key: "token")

    def fake_fetch_tiers(admin_url: str, token: str, http_get: Any) -> list[dict[str, Any]]:
        calls.append("fetch_tiers")
        return [{"id": "tier-id", "slug": "cidadao-mamute", "type": "paid"}]

    def fake_sync_tiers(db: object, tiers: list[dict[str, Any]]) -> list[str]:
        assert db is session
        calls.append("sync_tiers")
        return ["tier-id"]

    def fake_fetch_members(admin_url: str, token: str, http_get: Any) -> list[dict[str, Any]]:
        calls.append("fetch_members")
        return [{"email": "assinante@example.com"}]

    def fake_sync_members(
        db: object,
        members: list[dict[str, Any]],
    ) -> tuple[int, int, int]:
        assert db is session
        calls.append("sync_members")
        return (0, 1, 0)

    monkeypatch.setattr(ghost_reconcile, "fetch_ghost_tiers", fake_fetch_tiers)
    monkeypatch.setattr(ghost_reconcile, "sync_ghost_tiers", fake_sync_tiers)
    monkeypatch.setattr(ghost_reconcile, "fetch_ghost_members", fake_fetch_members)
    monkeypatch.setattr(ghost_reconcile, "sync_ghost_members", fake_sync_members)

    result = ghost_reconcile.run_ghost_reconciliation(session)

    assert result.action == "synced"
    assert result.tiers_updated == 1
    assert result.members_seen == 1
    assert result.projects_updated == 1
    assert calls == ["fetch_tiers", "sync_tiers", "fetch_members", "sync_members"]
