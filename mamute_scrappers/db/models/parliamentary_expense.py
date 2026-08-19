"""Modelo de gasto da cota parlamentar (CEAP/Camara e CEAPS/Senado) — CS-57.

Nao confundir com emenda parlamentar: emenda e verba que o parlamentar DESTINA
do orcamento; a cota e verba que ele GASTA com o proprio mandato (combustivel,
aluguel de escritorio, divulgacao, passagens).

Uma tabela para as duas casas, discriminadas por `house` — as taxonomias de
tipo de despesa sao diferentes e ficam como a fonte publica, sem normalizacao
inventada. A chave natural de upsert e (house, source_key): na Camara o
`ideDocumento` do CSV anual; no Senado o `id` da API de dados abertos; quando a
Camara nao publica `ideDocumento` (telefonia, correios), um hash deterministico
da linha.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


class ParliamentaryExpense(Base):
    __tablename__ = "parliamentary_expense"
    __table_args__ = (
        UniqueConstraint(
            "house", "source_key", name="uq_parliamentary_expense_house_source"
        ),
        # Toda consulta do produto filtra por parlamentar e ano.
        Index("ix_parliamentary_expense_parl_year", "parliamentarian_id", "year"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    house = Column(Text, nullable=False)  # 'camara' | 'senado'
    source_key = Column(Text, nullable=False)

    # SET NULL, como nas emendas: gasto publico e fato historico e nao deve
    # sumir se o parlamentar sair da base. Fica NULL para deputados de
    # legislaturas fora da base e para as liderancas partidarias.
    parliamentarian_id = Column(
        BigInteger,
        ForeignKey("parliamentarian.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)

    expense_type = Column(Text, nullable=False)
    supplier_name = Column(Text)
    supplier_id = Column(Text)  # CNPJ/CPF como a fonte publica (com mascara)
    document_number = Column(Text)
    document_date = Column(Date)
    details = Column(Text)

    # Camara publica documento/glosa/liquido; Senado so o reembolsado, que
    # entra em net_value com os outros dois nulos.
    document_value = Column(Numeric(18, 2))
    glosa_value = Column(Numeric(18, 2))
    net_value = Column(Numeric(18, 2), nullable=False)

    # Camara: PDF direto da nota. Senado: pagina de detalhe do portal de
    # transparencia (o id do PDF nao existe na API/CSV — ver spec CS-57).
    document_url = Column(Text)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    parliamentarian = relationship("Parliamentarian", back_populates="expenses")


__all__ = ["ParliamentaryExpense"]
