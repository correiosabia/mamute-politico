from __future__ import annotations

import pytest

from chatbot_backend.app.core.config import get_settings


def test_settings_load_openai_compatible_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("PGVECTOR_CONNECTION", "sqlite:///:memory:")
    get_settings.cache_clear()

    try:
        assert get_settings().openai_base_url == "https://openrouter.ai/api/v1"
    finally:
        get_settings.cache_clear()
