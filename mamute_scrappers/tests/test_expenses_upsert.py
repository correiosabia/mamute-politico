"""Upsert de gastos da cota parlamentar (CS-57).

Mesmo padrao de test_emendas_upsert: base local espelhando as colunas usadas,
SQLite em memoria, autoflush=False como em producao.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterator

import pytest
from sqlalchemy import (
    Column,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from mamute_scrappers.expenses import upsert as upsert_mod

Base = declarative_base()


class Parliamentarian(Base):
    __tablename__ = "parliamentarian"
    id = Column(Integer, primary_key=True)
    name = Column(Text)


class ParliamentaryExpense(Base):
    __tablename__ = "parliamentary_expense"
    __table_args__ = (
        UniqueConstraint("house", "source_key"),
    )
    id = Column(Integer, primary_key=True)
    house = Column(Text, nullable=False)
    source_key = Column(Text, nullable=False)
    parliamentarian_id = Column(Integer, ForeignKey("parliamentarian.id"))
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    expense_type = Column(Text, nullable=False)
    supplier_name = Column(Text)
    supplier_id = Column(Text)
    document_number = Column(Text)
    document_date = Column(Date)
    details = Column(Text)
    document_value = Column(Numeric(18, 2))
    glosa_value = Column(Numeric(18, 2))
    net_value = Column(Numeric(18, 2), nullable=False)
    document_url = Column(Text)


@pytest.fixture()
def session(monkeypatch) -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(upsert_mod, "ParliamentaryExpense", ParliamentaryExpense)
    with maker() as s:
        s.add(Parliamentarian(id=1, name="Danilo Forte"))
        s.commit()
        yield s


def _payload(**overrides):
    base = {
        "house": "camara",
        "source_key": "1:7883485:0",
        "parliamentarian_id": 1,
        "year": 2025,
        "month": 2,
        "expense_type": "MANUTENÇÃO DE ESCRITÓRIO",
        "supplier_name": "ALARES",
        "supplier_id": "633.560.420/0018-0",
        "document_number": "5771570",
        "document_date": None,
        "details": None,
        "document_value": Decimal("104.58"),
        "glosa_value": Decimal("0"),
        "net_value": Decimal("104.58"),
        "document_url": "https://example.test/doc.pdf",
    }
    base.update(overrides)
    return base


def test_cria_e_atualiza_sem_duplicar(session):
    _, created = upsert_mod.upsert_expense(session, _payload())
    assert created is True
    session.commit()

    record, created = upsert_mod.upsert_expense(
        session, _payload(net_value=Decimal("99.99"))
    )
    assert created is False
    session.commit()

    rows = session.query(ParliamentaryExpense).all()
    assert len(rows) == 1
    assert rows[0].net_value == Decimal("99.99")


def test_mesma_chave_em_casas_diferentes_nao_conflita(session):
    upsert_mod.upsert_expense(session, _payload())
    upsert_mod.upsert_expense(
        session, _payload(house="senado", parliamentarian_id=None)
    )
    session.commit()
    assert session.query(ParliamentaryExpense).count() == 2


def test_repetida_no_mesmo_lote_nao_estoura_unique(session):
    # A sessao usa autoflush=False e commit por lote: sem o flush interno do
    # upsert, a segunda ocorrencia no mesmo lote nao acharia a primeira e o
    # commit morreria com UniqueViolation.
    upsert_mod.upsert_expense(session, _payload())
    upsert_mod.upsert_expense(session, _payload(net_value=Decimal("1.00")))
    session.commit()
    rows = session.query(ParliamentaryExpense).all()
    assert len(rows) == 1
    assert rows[0].net_value == Decimal("1.00")


def test_sequenced_key_desambigua_chave_repetida_no_mesmo_arquivo():
    # Caso real do Ano-2025.csv: o bilhete SIGEPA aparece duas vezes com o
    # mesmo ideDocumento (compra e compensacao negativa). Sem o sufixo, a
    # segunda linha sobrescreveria a primeira e o par que se cancela sumiria.
    from collections import Counter

    seen: Counter = Counter()
    assert upsert_mod.sequenced_key("998:319264:0", seen) == "998:319264:0#0"
    assert upsert_mod.sequenced_key("998:319264:0", seen) == "998:319264:0#1"
    assert upsert_mod.sequenced_key("1:7883485:0", seen) == "1:7883485:0#0"


def test_fallback_source_key_deterministico():
    a = upsert_mod.fallback_source_key("62881", 2025, 1, "10", "CELULAR", "224.65")
    b = upsert_mod.fallback_source_key("62881", 2025, 1, "10", "CELULAR", "224.65")
    c = upsert_mod.fallback_source_key("62881", 2025, 2, "10", "CELULAR", "224.65")
    assert a == b
    assert a != c
    assert len(a) == 40
