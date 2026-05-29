from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import BigInteger, Column, Text, create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import Session, sessionmaker


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


camara_proposition = load_module(
    "test_camara_proposition",
    "mamute_scrappers/camara_crawler/proposition.py",
)
camara_proposition_type = load_module(
    "test_camara_proposition_type",
    "mamute_scrappers/camara_crawler/proposition_type.py",
)
senado_proposition = load_module(
    "test_senado_proposition",
    "mamute_scrappers/senado_crawler/proposition.py",
)
senado_proposition_type = load_module(
    "test_senado_proposition_type",
    "mamute_scrappers/senado_crawler/proposition_type.py",
)
senado_roll_call_votes = load_module(
    "test_senado_roll_call_votes",
    "mamute_scrappers/senado_crawler/roll_call_votes.py",
)
speech_text_analysis = load_module(
    "test_speech_text_analysis",
    "mamute_scrappers/senado_crawler/speech_text_analysis.py",
)

Base = declarative_base()


class PropositionType(Base):
    __tablename__ = "proposition_type"

    id = Column(BigInteger, primary_key=True)
    type = Column(Text)
    proposition_type_code = Column(Text)
    acronym = Column(Text)
    name = Column(Text)
    description = Column(Text)


class DummyRecord:
    proposition_type = None


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:", future=True)
    PropositionType.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    with SessionLocal() as db_session:
        yield db_session


@pytest.fixture(autouse=True)
def patch_modules() -> Iterator[None]:
    original_values = {
        senado_roll_call_votes: senado_roll_call_votes.PropositionTypeModel,
        senado_proposition: senado_proposition.PropositionType,
        senado_proposition_type: senado_proposition_type.PropositionType,
        camara_proposition: camara_proposition.PropositionType,
        camara_proposition_type: camara_proposition_type.PropositionType,
    }
    original_senado_status = senado_proposition.PropositionStatus

    senado_roll_call_votes.PropositionTypeModel = PropositionType
    senado_proposition.PropositionType = PropositionType
    senado_proposition.PropositionStatus = object
    senado_proposition_type.PropositionType = PropositionType
    camara_proposition.PropositionType = PropositionType
    camara_proposition_type.PropositionType = PropositionType

    yield

    for module, value in original_values.items():
        if module is senado_roll_call_votes:
            module.PropositionTypeModel = value
        else:
            module.PropositionType = value
    senado_proposition.PropositionStatus = original_senado_status


def test_senado_roll_call_uses_senado_type_when_acronym_is_duplicated(
    session: Session,
) -> None:
    session.add_all(
        [
            PropositionType(id=1, acronym="REQ", type="Camara", proposition_type_code="147"),
            PropositionType(id=2, acronym="REQ", type="Camara", proposition_type_code="1015"),
            PropositionType(id=3, acronym="REQ", type="Senado", name="REQ"),
        ]
    )
    session.flush()

    record = DummyRecord()

    senado_roll_call_votes._assign_type(
        session,
        record,
        {"proposition_sigla": "REQ"},
    )

    assert record.proposition_type is not None
    assert record.proposition_type.id == 3
    assert record.proposition_type.type == "Senado"


def test_senado_proposition_upsert_does_not_mutate_camara_type(
    session: Session,
) -> None:
    session.add_all(
        [
            PropositionType(id=1, acronym="REQ", type="Camara", description="Camara"),
            PropositionType(id=2, acronym="REQ", type="Senado", description="Old Senado"),
        ]
    )
    session.flush()

    record = senado_proposition_type._upsert_proposition_type(
        session,
        {
            "acronym": "REQ",
            "type": "Senado",
            "name": "REQ",
            "description": "New Senado",
        },
    )

    assert record.id == 2
    assert record.type == "Senado"
    assert record.description == "New Senado"
    assert session.get(PropositionType, 1).description == "Camara"


def test_senado_proposition_assign_type_uses_senado_scope(session: Session) -> None:
    session.add_all(
        [
            PropositionType(id=1, acronym="PL", type="Camara"),
            PropositionType(id=2, acronym="PL", type="Senado"),
        ]
    )
    session.flush()

    record = DummyRecord()

    senado_proposition._assign_type_and_status(
        session,
        record,
        {"proposition_type_acronym": "PL"},
    )

    assert record.proposition_type is not None
    assert record.proposition_type.id == 2


def test_camara_type_upsert_prefers_proposition_type_code(
    session: Session,
) -> None:
    session.add_all(
        [
            PropositionType(
                id=1,
                acronym="REQ",
                type="Camara",
                proposition_type_code="147",
                description="Old 147",
            ),
            PropositionType(
                id=2,
                acronym="REQ",
                type="Camara",
                proposition_type_code="1015",
                description="Old 1015",
            ),
        ]
    )
    session.flush()

    record = camara_proposition_type._upsert_proposition_type(
        session,
        {
            "acronym": "REQ",
            "type": "Camara",
            "name": "Requerimento",
            "description": "New 1015",
            "proposition_type_code": "1015",
        },
    )

    assert record.id == 2
    assert record.description == "New 1015"
    assert session.get(PropositionType, 1).description == "Old 147"


def test_camara_proposition_assign_type_handles_duplicate_codes(
    session: Session,
) -> None:
    session.add_all(
        [
            PropositionType(
                id=1,
                acronym="REQ",
                type="Camara",
                proposition_type_code="147",
            ),
            PropositionType(
                id=2,
                acronym="REQ",
                type="Camara",
                proposition_type_code="147",
            ),
        ]
    )
    session.flush()

    record = DummyRecord()

    camara_proposition._assign_type(
        session,
        record,
        {"proposition_type_code": "147", "proposition_code": 123},
    )

    assert record.proposition_type is not None
    assert record.proposition_type.id == 1


def test_default_spacy_model_prefers_installed_lightweight_model() -> None:
    assert speech_text_analysis.DEFAULT_MODEL_CANDIDATES[0] == "pt_core_news_sm"
