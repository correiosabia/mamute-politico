from __future__ import annotations

import importlib.util
import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    ForeignKey,
    Integer,
    Text,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "camara_plenary_attendance"


def load_module(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


camara_plenary_attendance = load_module(
    "test_camara_plenary_attendance_module",
    "mamute_scrappers/camara_crawler/plenary_attendance.py",
)

Base = declarative_base()


class Parliamentarian(Base):
    __tablename__ = "parliamentarian"

    id = Column(Integer, primary_key=True)
    type = Column(Text)
    parliamentarian_code = Column(BigInteger)
    name = Column(Text)


class PlenaryAttendance(Base):
    __tablename__ = "plenary_attendance"

    id = Column(Integer, primary_key=True)
    parliamentarian_id = Column(Integer, ForeignKey("parliamentarian.id"), nullable=False)
    date = Column(Date)
    description = Column(Text)
    session_attendance = Column(Text)
    daily_attendance_justification = Column(Text)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    with SessionLocal() as db_session:
        yield db_session


@pytest.fixture(autouse=True)
def patch_models() -> Iterator[None]:
    original_parliamentarian = camara_plenary_attendance.Parliamentarian
    original_plenary_attendance = camara_plenary_attendance.PlenaryAttendance

    camara_plenary_attendance.Parliamentarian = Parliamentarian
    camara_plenary_attendance.PlenaryAttendance = PlenaryAttendance

    yield

    camara_plenary_attendance.Parliamentarian = original_parliamentarian
    camara_plenary_attendance.PlenaryAttendance = original_plenary_attendance


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_build_attendance_payloads_marks_present_and_absent_deputies() -> None:
    event = load_fixture("event_80872.json")["dados"]
    participants = load_fixture("event_80872_deputados.json")["dados"]

    payloads = camara_plenary_attendance._build_attendance_payloads(
        event,
        participants,
        chamber_parliamentarian_codes=[62881, 66828, 69871],
    )

    assert camara_plenary_attendance._is_deliberative_plenary_event(event) is True
    assert len(payloads) == 3
    assert {payload["parliamentarian_code"] for payload in payloads} == {
        62881,
        66828,
        69871,
    }
    assert {payload["date"] for payload in payloads} == {date(2026, 2, 2)}
    assert all(
        payload["description"] == "Camara evento 80872: Sessão Deliberativa"
        for payload in payloads
    )

    statuses_by_code = {
        payload["parliamentarian_code"]: payload["session_attendance"]
        for payload in payloads
    }
    assert statuses_by_code[62881] == "Presente"
    assert statuses_by_code[66828] == "Presente"
    assert statuses_by_code[69871] == "Ausente"


def test_upsert_plenary_attendance_is_idempotent(session: Session) -> None:
    session.add_all(
        [
            Parliamentarian(
                id=1,
                type="Deputado",
                parliamentarian_code=62881,
                name="Danilo Forte",
            ),
            Parliamentarian(
                id=2,
                type="Deputado",
                parliamentarian_code=66828,
                name="Fausto Pinato",
            ),
            Parliamentarian(
                id=3,
                type="Deputado",
                parliamentarian_code=69871,
                name="Bacelar",
            ),
        ]
    )
    session.flush()

    event = load_fixture("event_80872.json")["dados"]
    participants = load_fixture("event_80872_deputados.json")["dados"]
    payloads = camara_plenary_attendance._build_attendance_payloads(
        event,
        participants,
        chamber_parliamentarian_codes=[62881, 66828, 69871],
    )

    first_results = [
        camara_plenary_attendance._upsert_plenary_attendance(session, payload)
        for payload in payloads
    ]
    second_results = [
        camara_plenary_attendance._upsert_plenary_attendance(session, payload)
        for payload in payloads
    ]

    assert [created for _, created in first_results] == [True, True, True]
    assert [created for _, created in second_results] == [False, False, False]
    assert session.query(PlenaryAttendance).count() == 3

    records_by_code = {}
    for record in session.query(PlenaryAttendance).all():
        parliamentarian = session.get(Parliamentarian, record.parliamentarian_id)
        assert parliamentarian is not None
        records_by_code[parliamentarian.parliamentarian_code] = record

    assert records_by_code[62881].session_attendance == "Presente"
    assert records_by_code[66828].session_attendance == "Presente"
    assert records_by_code[69871].session_attendance == "Ausente"
