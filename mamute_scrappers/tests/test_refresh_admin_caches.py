"""Testes da rotina diária de caches admin (refresh_admin_caches).

Carrega o módulo por caminho (mesmo padrão dos outros testes de scrappers) —
os imports pesados (requests, mamute_scrappers.db) são lazy dentro de main().
"""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rac = _load(
    "test_refresh_admin_caches_module",
    "mamute_scrappers/scripts/refresh_admin_caches.py",
)


class _Resp:
    def __init__(self, data: Any) -> None:
        self._data = data

    def raise_for_status(self) -> None:  # noqa: D401
        return None

    def json(self) -> Any:
        return self._data


# --------------------------------------------------------------------------- #
# Funções puras de contagem das APIs abertas.
# --------------------------------------------------------------------------- #
def test_parse_last_page() -> None:
    payload = {"links": [{"rel": "last", "href": "https://x/api?ano=2025&pagina=6520&itens=1"}]}
    assert rac.parse_last_page(payload) == 6520
    assert rac.parse_last_page({"dados": [1, 2, 3]}) == 3


def test_count_senado_materias() -> None:
    payload = {"PesquisaBasicaMateria": {"Materias": {"Materia": [{}, {}, {}]}}}
    assert rac.count_senado_materias(payload) == 3
    assert rac.count_senado_materias({"PesquisaBasicaMateria": {}}) == 0


def test_fetch_camara_count_uses_last_page() -> None:
    def http_get(url: str, **kwargs: Any) -> _Resp:
        return _Resp({"links": [{"rel": "last", "href": "https://x?pagina=17&itens=1"}]})

    assert rac.fetch_camara_count(2025, "PL", http_get) == 17


def test_fetch_senado_count_counts_materias() -> None:
    def http_get(url: str, **kwargs: Any) -> _Resp:
        return _Resp({"PesquisaBasicaMateria": {"Materias": {"Materia": [{}, {}]}}})

    assert rac.fetch_senado_count(2025, "PL", http_get) == 2


# --------------------------------------------------------------------------- #
# Snapshot da cobertura (espelha api/services/admin_coverage.py).
# --------------------------------------------------------------------------- #
def _coverage_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql("create table parliamentarian (id integer primary key, type text)")
        conn.exec_driver_sql(
            "create table proposition_type (id integer primary key, acronym text, name text)"
        )
        conn.exec_driver_sql(
            "create table proposition (id integer primary key, presentation_year integer, "
            "proposition_type_id integer)"
        )
        conn.exec_driver_sql(
            "create table authors_proposition (id integer primary key, proposition_id integer, "
            "parliamentarian_id integer)"
        )
        conn.exec_driver_sql("create table roll_call_votes (id integer primary key)")
        conn.exec_driver_sql("create table speeches_transcripts (id integer primary key)")
        conn.exec_driver_sql(
            "create table api_coverage (id integer primary key, source text, year integer, "
            "sigla_type text, api_count integer, synced_at datetime)"
        )
        conn.exec_driver_sql(
            "insert into api_coverage (source, year, sigla_type, api_count) values "
            "('camara',2025,'PL',2),('senado',2025,'PL',4)"
        )
        conn.exec_driver_sql(
            "insert into parliamentarian (id, type) values (1,'deputado'),(2,'senador')"
        )
        conn.exec_driver_sql(
            "insert into proposition_type (id, acronym, name) values (1,'PL','Projeto de Lei'),(2,'PEC','Emenda')"
        )
        conn.exec_driver_sql(
            "insert into proposition (id, presentation_year, proposition_type_id) values "
            "(1,2025,1),(2,2025,2),(3,2024,1)"
        )
        conn.exec_driver_sql(
            "insert into authors_proposition (proposition_id, parliamentarian_id) values (1,1),(2,2)"
        )
        conn.exec_driver_sql("insert into roll_call_votes (id) values (1),(2)")
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_build_coverage_payload_matches_live_logic() -> None:
    payload = rac.build_coverage_payload(_coverage_session())

    by_year = {r["year"]: r for r in payload["by_year_house"]}
    assert by_year[2025]["camara"] == 1
    assert by_year[2025]["senado"] == 1
    assert by_year[2025]["total"] == 2
    assert by_year[2025]["cobertura_camara_pct"] == 50.0
    assert by_year[2025]["cobertura_senado_pct"] == 25.0
    assert by_year[2024]["desconhecido"] == 1

    by_type = {t["type"]: t["count"] for t in payload["by_type"]}
    assert by_type["PL"] == 2
    assert by_type["PEC"] == 1
    assert payload["totals"] == {"proposicoes": 3, "votacoes": 2, "discursos": 0}


# --------------------------------------------------------------------------- #
# Câmbio USD→BRL: upsert idempotente.
# --------------------------------------------------------------------------- #
def _rate_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "create table usd_brl_rate (rate_date date primary key, bid numeric, "
            "fetched_at datetime default current_timestamp)"
        )
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_fetch_usd_brl_bid() -> None:
    def http_get(url: str, **kwargs: Any) -> _Resp:
        return _Resp({"USDBRL": {"bid": "6.1234"}})

    assert rac.fetch_usd_brl_bid(http_get) == 6.1234


def test_store_usd_brl_rate_upserts() -> None:
    session = _rate_session()
    today = date(2026, 7, 5)
    rac.store_usd_brl_rate(session, 6.10, today)
    rac.store_usd_brl_rate(session, 6.25, today)  # mesmo dia → atualiza, não duplica
    session.commit()

    rows = session.execute(
        text("SELECT rate_date, bid FROM usd_brl_rate")
    ).all()
    assert len(rows) == 1
    assert float(rows[0][1]) == 6.25
