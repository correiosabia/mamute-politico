from __future__ import annotations

from decimal import Decimal
from typing import Iterator

import pytest
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from mamute_scrappers.portal_crawler import emendas as emendas_mod

# Base local espelhando so as colunas usadas pelo upsert, para rodar em SQLite
# em memoria sem depender do modelo real (que exige DATABASE_URL no import).
#
# As PKs sao Integer, e nao BigInteger como em producao: o SQLite so
# auto-incrementa "INTEGER PRIMARY KEY". O tipo real da coluna esta coberto pelo
# alembic upgrade contra Postgres, nao por este espelho.
Base = declarative_base()


class Parliamentarian(Base):
    __tablename__ = "parliamentarian"
    id = Column(Integer, primary_key=True)
    name = Column(Text)
    full_name = Column(Text)


class ParliamentaryAmendment(Base):
    __tablename__ = "parliamentary_amendment"
    id = Column(Integer, primary_key=True)
    amendment_code = Column(Text, nullable=False, unique=True)
    year = Column(Integer)
    amendment_number = Column(Text)
    amendment_type = Column(Text)
    author_name_raw = Column(Text)
    author_raw = Column(Text)
    parliamentarian_id = Column(Integer, ForeignKey("parliamentarian.id"))
    match_status = Column(Text, nullable=False)
    spending_locality = Column(Text)
    function = Column(Text)
    subfunction = Column(Text)
    committed_value = Column(Numeric(18, 2))
    settled_value = Column(Numeric(18, 2))
    paid_value = Column(Numeric(18, 2))
    remainder_inscribed = Column(Numeric(18, 2))
    remainder_cancelled = Column(Numeric(18, 2))
    remainder_paid = Column(Numeric(18, 2))


@pytest.fixture()
def session(monkeypatch) -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    # autoflush=False espelha a sessao de producao (db/engine.py). Com
    # autoflush=True o bug de duplicata dentro do lote nao reproduz.
    maker = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(emendas_mod, "ParliamentaryAmendment", ParliamentaryAmendment)
    with maker() as s:
        s.add(
            Parliamentarian(
                id=1, name="Heitor Schuch", full_name="Heitor José Schuch"
            )
        )
        s.commit()
        yield s


def payload(**overrides):
    base = {
        "amendment_code": "202632980010",
        "year": 2026,
        "amendment_number": "0010",
        "amendment_type": "Emenda Individual - Transferências com Finalidade Definida",
        "author_name_raw": "HEITOR SCHUCH",
        "author_raw": "HEITOR SCHUCH",
        "parliamentarian_id": 1,
        "match_status": "matched",
        "spending_locality": "RIO GRANDE DO SUL (UF)",
        "function": "Assistência social",
        "subfunction": "Alimentação e nutrição",
        "committed_value": Decimal("0.00"),
        "settled_value": Decimal("1099734.20"),
        "paid_value": Decimal("0.00"),
        "remainder_inscribed": None,
        "remainder_cancelled": None,
        "remainder_paid": None,
    }
    base.update(overrides)
    return base


def test_primeira_gravacao_cria_registro(session):
    record, created = emendas_mod.upsert_amendment(session, payload())
    session.commit()

    assert created is True
    assert record.amendment_code == "202632980010"
    assert session.query(ParliamentaryAmendment).count() == 1


def test_segunda_gravacao_atualiza_sem_duplicar(session):
    emendas_mod.upsert_amendment(session, payload())
    session.commit()

    emendas_mod.upsert_amendment(session, payload(paid_value=Decimal("500000.00")))
    session.commit()

    assert session.query(ParliamentaryAmendment).count() == 1
    record = session.query(ParliamentaryAmendment).one()
    assert record.paid_value == Decimal("500000.00")


def test_correcao_manual_nao_e_sobrescrita_pelo_robo(session):
    emendas_mod.upsert_amendment(
        session, payload(parliamentarian_id=None, match_status="unmatched")
    )
    session.commit()

    # Um humano corrigiu no painel de administracao.
    record = session.query(ParliamentaryAmendment).one()
    record.parliamentarian_id = 1
    record.match_status = "manual"
    session.commit()

    # O crawler roda de novo e continua sem conseguir casar.
    emendas_mod.upsert_amendment(
        session,
        payload(
            parliamentarian_id=None,
            match_status="unmatched",
            paid_value=Decimal("77.00"),
        ),
    )
    session.commit()

    record = session.query(ParliamentaryAmendment).one()
    assert record.parliamentarian_id == 1
    assert record.match_status == "manual"
    # Mas o valor financeiro continua sendo atualizado.
    assert record.paid_value == Decimal("77.00")


def test_casamento_novo_substitui_o_anterior_quando_nao_e_manual(session):
    emendas_mod.upsert_amendment(
        session, payload(parliamentarian_id=None, match_status="unmatched")
    )
    session.commit()

    emendas_mod.upsert_amendment(
        session, payload(parliamentarian_id=1, match_status="matched")
    )
    session.commit()

    record = session.query(ParliamentaryAmendment).one()
    assert record.parliamentarian_id == 1
    assert record.match_status == "matched"


def test_emenda_nao_casada_e_persistida_e_nao_descartada(session):
    emendas_mod.upsert_amendment(
        session,
        payload(
            amendment_code="X1",
            author_name_raw="FATIMA PELAES",
            parliamentarian_id=None,
            match_status="unmatched",
        ),
    )
    session.commit()

    record = (
        session.query(ParliamentaryAmendment)
        .filter(ParliamentaryAmendment.amendment_code == "X1")
        .one()
    )
    assert record.parliamentarian_id is None
    assert record.match_status == "unmatched"
    assert record.author_name_raw == "FATIMA PELAES"


def test_codigo_repetido_no_mesmo_lote_nao_gera_duplicata(session):
    """Regressao: o Portal repete o mesmo codigoEmenda entre paginas.

    Como a sessao usa autoflush=False e o commit so ocorre a cada 500 registros,
    sem flush no insert a segunda ocorrencia nao enxergava o INSERT pendente,
    criava duplicata e o commit morria com UniqueViolation — derrubando o ano
    inteiro. Aconteceu em producao com o ano 2023 (codigo 202339950016).
    """
    emendas_mod.upsert_amendment(session, payload(amendment_code="202339950016"))
    # Sem commit no meio, exatamente como dentro do lote de 500.
    _, created = emendas_mod.upsert_amendment(
        session,
        payload(amendment_code="202339950016", paid_value=Decimal("123.45")),
    )
    session.commit()

    assert created is False
    assert session.query(ParliamentaryAmendment).count() == 1
    assert session.query(ParliamentaryAmendment).one().paid_value == Decimal("123.45")
