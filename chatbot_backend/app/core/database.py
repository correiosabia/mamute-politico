"""Configuração da conexão com o banco relacional utilizado nas consultas SQL."""

from __future__ import annotations

from contextlib import contextmanager
import logging
from typing import Generator
from urllib.parse import urlparse

from sqlalchemy import event
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

_settings = get_settings()
logger = logging.getLogger(__name__)

_connect_args: dict[str, str] = {}
if _settings.database_url.startswith("postgresql"):
    _connect_args["application_name"] = _settings.application_name

_engine_kwargs: dict[str, object] = {
    "pool_pre_ping": True,
    "future": True,
}
if _connect_args:
    _engine_kwargs["connect_args"] = _connect_args

engine: Engine = create_engine(_settings.database_url, **_engine_kwargs)


@event.listens_for(engine, "connect")
def _log_mamute_db_connection(_dbapi_connection: object, _connection_record: object) -> None:
    """Loga cada nova conexão criada para o banco relacional."""

    parsed = urlparse(_settings.database_url)
    logger.info(
        "🦣 Mamute DB connected | host=%s | port=%s | database=%s | application_name=%s",
        parsed.hostname or "unknown",
        parsed.port or "default",
        parsed.path.lstrip("/") or "unknown",
        _settings.application_name,
    )

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Gera uma sessão SQLAlchemy garantindo o fechamento apropriado."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


__all__ = ["engine", "SessionLocal", "get_session"]
