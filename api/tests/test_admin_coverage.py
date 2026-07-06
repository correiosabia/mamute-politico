"""db_coverage agora só LÊ o snapshot (o cálculo mora nos scrappers)."""
from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.services.admin_coverage import db_coverage

_PAYLOAD = {
    "kpis": {"proposicoes": 42, "discursos": 10, "votacoes_nominais": 3, "parlamentares": 639},
    "proposicoes": {
        "camara": [
            {"year": 2025, "nosso": 100, "oficial": 48, "pct": 208.3, "status": "superset"}
        ],
        "senado": [{"year": 2025, "nosso": 7}],
        "nota_superset": "sub-documentos",
    },
    "discursos": {"camara": [], "senado": [], "nota": "x"},
    "votacoes": {"camara": [], "senado": [], "nota": "y"},
    "parlamentares": {
        "deputados": {"nossa_base": 553, "cadeiras": 513, "status": "completo"},
        "senadores": {"nossa_base": 86, "cadeiras": 81, "status": "completo"},
        "nota": "suplentes",
    },
    "consolidado": [],
}


def _engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _session_with_snapshot() -> Session:
    engine = _engine()
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "create table coverage_snapshot (id integer primary key, "
            "payload text not null, computed_at text)"
        )
        conn.exec_driver_sql(
            "insert into coverage_snapshot (payload, computed_at) values (:p, :t)",
            {"p": json.dumps(_PAYLOAD), "t": "2026-07-06T04:00:00"},
        )
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_db_coverage_serves_snapshot() -> None:
    cov = db_coverage(_session_with_snapshot())
    assert cov["pending"] is False
    assert cov["computed_at"] == "2026-07-06T04:00:00"
    assert cov["kpis"]["proposicoes"] == 42
    assert cov["proposicoes"]["camara"][0]["status"] == "superset"
    assert cov["parlamentares"]["deputados"]["nossa_base"] == 553


def test_db_coverage_pending_when_table_missing() -> None:
    session = sessionmaker(bind=_engine(), expire_on_commit=False)()
    cov = db_coverage(session)
    assert cov["pending"] is True
    assert cov["computed_at"] is None
    assert cov["kpis"] == {}


def test_db_coverage_pending_when_snapshot_empty() -> None:
    engine = _engine()
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "create table coverage_snapshot (id integer primary key, "
            "payload text not null, computed_at text)"
        )
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    assert db_coverage(session)["pending"] is True
