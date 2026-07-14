"""email_send_log: cada tentativa de envio vira uma linha; falha de log não quebra."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


send_log = _load(
    "test_notificacao_send_log_mod",
    "mamute_scrappers/scripts/notificacao/send_log.py",
)
STATUS_ERROR = send_log.STATUS_ERROR
STATUS_SENT = send_log.STATUS_SENT
log_send_attempt = send_log.log_send_attempt


def _session(create_table: bool = True) -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    if create_table:
        with engine.begin() as c:
            c.exec_driver_sql(
                "CREATE TABLE email_send_log ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "projeto_id BIGINT NOT NULL, email TEXT NOT NULL, "
                "periodicidade TEXT NOT NULL, status TEXT NOT NULL, "
                "detail TEXT, subject TEXT, stats JSON, "
                "period_start DATE, period_end DATE, "
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
    return Session(engine)


def test_log_sent_writes_row_with_stats() -> None:
    session = _session()
    log_send_attempt(
        session,
        projeto_id=7,
        email="a@b.c",
        periodicidade="fortnight",
        status=STATUS_SENT,
        subject="Relatório quinzenal",
        stats={"proposicoes": 2, "discursos": 1},
    )
    row = session.execute(
        text("SELECT projeto_id, email, periodicidade, status, subject, stats FROM email_send_log")
    ).one()
    assert row.projeto_id == 7
    assert row.email == "a@b.c"
    assert row.periodicidade == "fortnight"
    assert row.status == STATUS_SENT
    assert row.subject == "Relatório quinzenal"
    assert "proposicoes" in row.stats


def test_log_error_records_detail() -> None:
    session = _session()
    log_send_attempt(
        session,
        projeto_id=9,
        email="x@y.z",
        periodicidade="week",
        status=STATUS_ERROR,
        detail="SMTP timeout",
    )
    row = session.execute(
        text("SELECT status, detail FROM email_send_log")
    ).one()
    assert row.status == STATUS_ERROR
    assert row.detail == "SMTP timeout"


def test_missing_table_never_raises() -> None:
    session = _session(create_table=False)
    # tabela ausente (ex.: migration ainda não aplicada) → só warning, sem exceção
    log_send_attempt(
        session,
        projeto_id=1,
        email="a@b.c",
        periodicidade="day",
        status=STATUS_SENT,
    )
