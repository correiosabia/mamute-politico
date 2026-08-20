from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import (
    Column,
    Date,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from mamute_scrappers.tse_crawler import consulta_cand as consulta_mod
from mamute_scrappers.tse_crawler.profile import (
    PROFILE_SOURCE_API,
    PROFILE_SOURCE_CSV,
)

# Base local espelhando so as colunas usadas pelo upsert, para rodar em SQLite
# em memoria — mesma abordagem de test_tse_candidacy_upsert.py.
Base = declarative_base()


class Parliamentarian(Base):
    __tablename__ = "parliamentarian"
    id = Column(Integer, primary_key=True)


class Candidacy(Base):
    __tablename__ = "candidacy"
    __table_args__ = (
        UniqueConstraint("election_year", "state", "tse_candidate_id"),
    )
    id = Column(Integer, primary_key=True)
    election_year = Column(Integer, nullable=False)
    tse_candidate_id = Column(Integer, nullable=False)
    office_code = Column(Integer)
    office = Column(Text)
    state = Column(Text)
    ballot_number = Column(Integer)
    ballot_name = Column(Text)
    full_name = Column(Text)
    party = Column(Text)
    coalition = Column(Text)
    status = Column(Text)
    totalization_status = Column(Text)
    cpf = Column(Text)
    voter_id = Column(Text)
    birth_date = Column(Date)
    gender = Column(Text)
    race = Column(Text)
    education = Column(Text)
    occupation = Column(Text)
    marital_status = Column(Text)
    nationality = Column(Text)
    federation = Column(Text)
    profile_source = Column(Text)
    parliamentarian_id = Column(Integer, ForeignKey("parliamentarian.id"))
    match_status = Column(Text)


@pytest.fixture()
def session(monkeypatch) -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(consulta_mod, "Candidacy", Candidacy)
    with maker() as s:
        s.add(Parliamentarian(id=1))
        s.commit()
        yield s


def csv_row(**overrides):
    base = {
        "SQ_CANDIDATO": "10001635769",
        "NR_TURNO": "1",
        "CD_CARGO": "7",
        "DS_CARGO": "DEPUTADO ESTADUAL",
        "SG_UF": "AC",
        "NR_CANDIDATO": "13123",
        "NM_URNA_CANDIDATO": "PROFESSOR FULANO",
        "NM_CANDIDATO": "FULANO DE TAL",
        "SG_PARTIDO": "PT",
        "NM_COLIGACAO": "#NULO#",
        "DS_SITUACAO_CANDIDATURA": "APTO",
        "DS_SIT_TOT_TURNO": "SUPLENTE",
        "NR_CPF_CANDIDATO": "12345678901",
        "NR_TITULO_ELEITORAL_CANDIDATO": "003576712402",
        "DT_NASCIMENTO": "09/09/2000",
        "DS_GENERO": "MASCULINO",
        "DS_COR_RACA": "INDÍGENA",
        "DS_GRAU_INSTRUCAO": "SUPERIOR INCOMPLETO",
        "DS_OCUPACAO": "ESTUDANTE",
        "DS_ESTADO_CIVIL": "SOLTEIRO(A)",
        "DS_NACIONALIDADE": None,
        "SG_FEDERACAO": "PT/PC do B/PV",
    }
    base.update(overrides)
    return base


def payload(**overrides):
    built = consulta_mod.build_csv_payload(csv_row(), year=2022)
    built.pop("turno", None)
    built["parliamentarian_id"] = None
    built["match_status"] = "unmatched"
    built.update(overrides)
    return built


def test_build_payload_normaliza_e_chaveia():
    built = consulta_mod.build_csv_payload(csv_row(), year=2022)
    assert built["election_year"] == 2022
    assert built["tse_candidate_id"] == 10001635769
    assert built["turno"] == 1
    assert built["coalition"] is None  # sentinela #NULO#
    assert built["race"] == "INDÍGENA"
    assert built["federation"] == "PT/PC DO B/PV"
    assert built["profile_source"] == PROFILE_SOURCE_CSV


def test_build_payload_descarta_sentinela_em_voter_id():
    # 1994/1998 vem com NR_TITULO_ELEITORAL_CANDIDATO = "#NE".
    built = consulta_mod.build_csv_payload(
        csv_row(NR_TITULO_ELEITORAL_CANDIDATO="#NE"), year=1998
    )
    assert built["voter_id"] is None


def test_build_payload_sem_sq_retorna_none():
    assert consulta_mod.build_csv_payload(csv_row(SQ_CANDIDATO=""), year=2022) is None


def test_dedupe_segundo_turno_prevalece_turno_maior():
    primeiro = consulta_mod.build_csv_payload(
        csv_row(DS_SIT_TOT_TURNO="2º TURNO"), year=2022
    )
    segundo = consulta_mod.build_csv_payload(
        csv_row(NR_TURNO="2", DS_SIT_TOT_TURNO="ELEITO"), year=2022
    )
    by_key = consulta_mod.dedupe_second_round([segundo, primeiro])
    assert len(by_key) == 1
    assert by_key[("AC", 10001635769)]["totalization_status"] == "ELEITO"


def test_dedupe_nao_mistura_ufs_com_mesmo_sq():
    # 2002/2006: SQ_CANDIDATO e sequencial POR UF — "119" existe em 26 UFs.
    ac = consulta_mod.build_csv_payload(csv_row(SQ_CANDIDATO="119"), year=2002)
    al = consulta_mod.build_csv_payload(
        csv_row(SQ_CANDIDATO="119", SG_UF="AL", NM_CANDIDATO="OUTRA PESSOA"),
        year=2002,
    )
    by_key = consulta_mod.dedupe_second_round([ac, al])
    assert len(by_key) == 2


def test_upsert_mesmo_sq_em_ufs_diferentes_cria_duas_linhas(session):
    consulta_mod.upsert_csv_candidacy(session, payload(tse_candidate_id=119))
    _, created = consulta_mod.upsert_csv_candidacy(
        session, payload(tse_candidate_id=119, state="AL")
    )
    session.commit()
    assert created is True
    assert session.query(Candidacy).count() == 2


def test_upsert_cria_linha_csv(session):
    record, created = consulta_mod.upsert_csv_candidacy(session, payload())
    session.commit()
    assert created is True
    assert record.profile_source == PROFILE_SOURCE_CSV
    assert record.education == "SUPERIOR INCOMPLETO"


def test_upsert_reexecucao_sobrescreve_linha_csv(session):
    consulta_mod.upsert_csv_candidacy(session, payload())
    session.commit()
    _, created = consulta_mod.upsert_csv_candidacy(
        session, payload(totalization_status="ELEITO")
    )
    session.commit()
    assert created is False
    record = session.query(Candidacy).one()
    assert record.totalization_status == "ELEITO"


def test_upsert_nao_sobrescreve_linha_da_api_so_completa_null(session):
    # Linha de 2026 vinda da DivulgaCandContas: status mais fresco que o CSV.
    session.add(
        Candidacy(
            election_year=2022,
            state="AC",
            tse_candidate_id=10001635769,
            status="Aguardando julgamento",
            education="SUPERIOR INCOMPLETO",
            federation=None,
            profile_source=PROFILE_SOURCE_API,
            parliamentarian_id=1,
            match_status="cpf",
        )
    )
    session.commit()

    _, created = consulta_mod.upsert_csv_candidacy(
        session, payload(status="APTO", education="SUPERIOR COMPLETO")
    )
    session.commit()

    assert created is False
    record = session.query(Candidacy).one()
    # Campos preenchidos pela API permanecem.
    assert record.status == "Aguardando julgamento"
    assert record.education == "SUPERIOR INCOMPLETO"
    assert record.profile_source == PROFILE_SOURCE_API
    assert record.parliamentarian_id == 1
    assert record.match_status == "cpf"
    # NULLs sao completados pelo CSV (federacao nao existe na API).
    assert record.federation == "PT/PC DO B/PV"


def test_upsert_respeita_match_manual(session):
    consulta_mod.upsert_csv_candidacy(session, payload())
    session.commit()
    record = session.query(Candidacy).one()
    record.match_status = "manual"
    record.parliamentarian_id = 1
    session.commit()

    consulta_mod.upsert_csv_candidacy(
        session, payload(parliamentarian_id=None, match_status="unmatched")
    )
    session.commit()
    record = session.query(Candidacy).one()
    assert record.match_status == "manual"
    assert record.parliamentarian_id == 1
