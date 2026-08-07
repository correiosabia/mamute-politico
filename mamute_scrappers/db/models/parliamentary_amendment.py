"""Modelo de emenda parlamentar orcamentaria.

Nao confundir com emenda a proposicao (alteracao de texto de projeto de lei),
que vive em `proposition_type`. Aqui e destinacao de verba do orcamento federal,
coletada do Portal da Transparencia.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


class ParliamentaryAmendment(Base):
    __tablename__ = "parliamentary_amendment"

    id = Column(BigInteger, primary_key=True, index=True)
    amendment_code = Column(Text, nullable=False, unique=True, index=True)
    year = Column(Integer, index=True)
    amendment_number = Column(Text)
    amendment_type = Column(Text)

    # `autor` e `nomeAutor` vieram sempre iguais na fonte (0 divergencias em 225
    # itens medidos). `author_raw` fica por fidelidade, caso passem a diferir.
    author_name_raw = Column(Text)
    author_raw = Column(Text)

    # SET NULL, e nao CASCADE como nas demais tabelas ligadas a parlamentar: a
    # emenda e fato orcamentario publico e nao deve sumir se o parlamentar sair
    # da base.
    parliamentarian_id = Column(
        BigInteger,
        ForeignKey("parliamentarian.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    match_status = Column(Text, nullable=False, index=True)

    spending_locality = Column(Text)
    function = Column(Text)
    subfunction = Column(Text)

    committed_value = Column(Numeric(18, 2))
    settled_value = Column(Numeric(18, 2))
    paid_value = Column(Numeric(18, 2))
    remainder_inscribed = Column(Numeric(18, 2))
    remainder_cancelled = Column(Numeric(18, 2))
    remainder_paid = Column(Numeric(18, 2))

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    parliamentarian = relationship("Parliamentarian", back_populates="amendments")


__all__ = ["ParliamentaryAmendment"]
