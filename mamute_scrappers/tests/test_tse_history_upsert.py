from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Iterator

import pytest
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from mamute_scrappers.tse_crawler import electoral_history as eh_mod

# Espelho minimo em SQLite, mesmo racional de test_tse_candidacy_upsert.py.
Base = declarative_base()

FIXED_DT = datetime(2026, 8, 9, 12, 0)


class Parliamentarian(Base):
    __tablename__ = "parliamentarian"
    id = Column(Integer, primary_key=True)


class Candidacy(Base):
    __tablename__ = "candidacy"
    id = Column(Integer, primary_key=True)
    election_year = Column(Integer)
    tse_candidate_id = Column(Integer)
    parliamentarian_id = Column(Integer, ForeignKey("parliamentarian.id"))


class ElectoralHistory(Base):
    __tablename__ = "electoral_history"
    __table_args__ = (UniqueConstraint("election_year", "tse_candidate_id"),)
    id = Column(Integer, primary_key=True)
    election_year = Column(Integer, nullable=False)
    tse_candidate_id = Column(Integer, nullable=False)
    tse_election_id = Column(Integer)
    parliamentarian_id = Column(Integer, ForeignKey("parliamentarian.id"))
    candidacy_id = Column(Integer, ForeignKey("candidacy.id"))
    office = Column(Text)
    state = Column(Text)
    locality = Column(Text)
    party = Column(Text)
    ballot_name = Column(Text)
    full_name = Column(Text)
    ballot_number = Column(Integer)
    result = Column(Text)
    declared_assets = Column(Numeric(18, 2))
    assets_count = Column(Integer)
    assets = Column(Text)
    assets_fetched_at = Column(Text)
    source_link = Column(Text)


@pytest.fixture()
def session(monkeypatch) -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(eh_mod, "ElectoralHistory", ElectoralHistory)
    monkeypatch.setattr(eh_mod, "Candidacy", Candidacy)
    monkeypatch.setattr(eh_mod, "Parliamentarian", Parliamentarian)
    with maker() as s:
        s.add(Parliamentarian(id=1))
        s.add(Candidacy(id=1, election_year=2026, tse_candidate_id=99, parliamentarian_id=1))
        s.commit()
        yield s


def payload(**overrides):
    base = {
        "election_year": 2022,
        "tse_candidate_id": 160001621846,
        "tse_election_id": 2040602022,
        "office": "Senador",
        "state": "PR",
        "locality": "PARANÁ",
        "party": "UNIÃO",
        "ballot_name": "SERGIO MORO",
        "full_name": "SERGIO FERNANDO MORO",
        "ballot_number": 444,
        "result": "Eleito",
        "source_link": "https://divulgacandcontas.tse.jus.br/divulga/#/candidato/2022/2040602022/PR/160001621846",
        "candidacy_id": None,
        "parliamentarian_id": None,
    }
    base.update(overrides)
    return base


def test_primeira_gravacao_cria(session):
    record, created = eh_mod.upsert_history(session, payload())
    session.commit()
    assert created is True
    assert record.result == "Eleito"
    assert session.query(ElectoralHistory).count() == 1


def test_upsert_atualiza_resultado_sem_duplicar(session):
    eh_mod.upsert_history(session, payload())
    session.commit()
    _, created = eh_mod.upsert_history(session, payload(result="Não eleito"))
    session.commit()
    assert created is False
    assert session.query(ElectoralHistory).one().result == "Não eleito"


def test_reseed_sem_vinculo_nao_apaga_vinculo_existente(session):
    eh_mod.upsert_history(session, payload(parliamentarian_id=1, candidacy_id=1))
    session.commit()
    eh_mod.upsert_history(session, payload(parliamentarian_id=None, candidacy_id=None))
    session.commit()
    row = session.query(ElectoralHistory).one()
    assert row.parliamentarian_id == 1
    assert row.candidacy_id == 1


def test_payload_sem_assets_nao_apaga_assets(session):
    com_assets = payload()
    com_assets.update(
        {
            "declared_assets": Decimal("100.00"),
            "assets_count": 1,
            "assets": '[{"valor": 100.0}]',
            "assets_fetched_at": FIXED_DT.isoformat(),
        }
    )
    eh_mod.upsert_history(session, com_assets)
    session.commit()

    eh_mod.upsert_history(session, payload(result="Eleito"))
    session.commit()

    row = session.query(ElectoralHistory).one()
    assert row.declared_assets == Decimal("100.00")
    assert row.assets_fetched_at is not None


def test_repeticao_no_mesmo_lote_nao_duplica(session):
    eh_mod.upsert_history(session, payload())
    _, created = eh_mod.upsert_history(session, payload())
    session.commit()
    assert created is False
    assert session.query(ElectoralHistory).count() == 1
