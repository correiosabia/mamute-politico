"""DB (tier_details) deve ganhar do env em resolve_monthly_limit."""
from __future__ import annotations

import pytest

from chatbot_backend.app.core.config import get_settings
from chatbot_backend.app.services.quota import ChatProject, resolve_monthly_limit


def _project(details: dict, product_id: str = "cidadao-mamute") -> ChatProject:
    return ChatProject(
        id=1,
        email="user@x.com",
        product_id=product_id,
        tier_slug=product_id,
        tier_details=details,
    )


def test_db_details_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MAMUTE_TIER_LIMITS_JSON",
        '{"cidadao-mamute": {"qtd_consultas_ia_mes": 50}}',
    )
    get_settings.cache_clear()
    assert resolve_monthly_limit(_project({"qtd_consultas_ia_mes": 200})) == 200


def test_env_used_when_db_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MAMUTE_TIER_LIMITS_JSON",
        '{"cidadao-mamute": {"qtd_consultas_ia_mes": 50}}',
    )
    get_settings.cache_clear()
    assert resolve_monthly_limit(_project({})) == 50
