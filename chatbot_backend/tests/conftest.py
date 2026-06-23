from __future__ import annotations

import os


os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("PGVECTOR_CONNECTION", "sqlite:///:memory:")
