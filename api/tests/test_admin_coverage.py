"""Cobertura do banco: contagens por ano, casa (via autor) e tipo."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.services.admin_coverage import db_coverage


def _session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "create table parliamentarian (id integer primary key, type text)"
        )
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
            "insert into parliamentarian (id, type) values (1,'deputado'),(2,'senador')"
        )
        conn.exec_driver_sql(
            "insert into proposition_type (id, acronym, name) values (1,'PL','Projeto de Lei'),(2,'PEC','Emenda')"
        )
        # prop1 2025 PL autor deputado (camara); prop2 2025 PEC autor senador (senado);
        # prop3 2024 PL sem autor (desconhecido)
        conn.exec_driver_sql(
            "insert into proposition (id, presentation_year, proposition_type_id) values "
            "(1,2025,1),(2,2025,2),(3,2024,1)"
        )
        conn.exec_driver_sql(
            "insert into authors_proposition (proposition_id, parliamentarian_id) values (1,1),(2,2)"
        )
        conn.exec_driver_sql("insert into roll_call_votes (id) values (1),(2)")
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_coverage_by_year_house_type() -> None:
    cov = db_coverage(_session())

    by_year = {r["year"]: r for r in cov["by_year_house"]}
    assert by_year[2025]["camara"] == 1
    assert by_year[2025]["senado"] == 1
    assert by_year[2025]["total"] == 2
    assert by_year[2024]["desconhecido"] == 1

    by_type = {t["type"]: t["count"] for t in cov["by_type"]}
    assert by_type["PL"] == 2
    assert by_type["PEC"] == 1

    assert cov["totals"]["proposicoes"] == 3
    assert cov["totals"]["votacoes"] == 2
    assert cov["totals"]["discursos"] == 0
