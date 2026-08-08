"""Modelo de candidatura eleitoral (TSE/DivulgaCandContas).

Uma linha por candidatura por eleicao, chaveada pelo id do candidato na
DivulgaCandContas. `parliamentarian_id` e anulavel: a maioria dos ~29 mil
candidatos de 2026 nao e parlamentar em exercicio, e o vinculo existe para
mostrar "este parlamentar e candidato a X". ON DELETE SET NULL, como nas
emendas: candidatura e fato publico e nao some com o parlamentar.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


class Candidacy(Base):
    __tablename__ = "candidacy"
    __table_args__ = (
        UniqueConstraint(
            "election_year", "tse_candidate_id", name="uq_candidacy_election_tse_id"
        ),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    election_year = Column(Integer, nullable=False, index=True)
    tse_candidate_id = Column(BigInteger, nullable=False)

    office_code = Column(Integer, index=True)
    office = Column(Text)
    state = Column(Text, index=True)

    ballot_number = Column(Integer)
    ballot_name = Column(Text)
    full_name = Column(Text)
    party = Column(Text)
    coalition = Column(Text)
    status = Column(Text)
    totalization_status = Column(Text)

    cpf = Column(Text)
    voter_id = Column(Text)
    photo_url = Column(Text)
    tse_last_update = Column(DateTime)

    # So e gravado apos upsert completo com detalhe; ausencia forca nova
    # tentativa de detalhe na proxima execucao.
    listing_fingerprint = Column(Text)

    parliamentarian_id = Column(
        BigInteger,
        ForeignKey("parliamentarian.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    match_status = Column(Text, nullable=False, index=True)

    details = Column(JSONB)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    parliamentarian = relationship("Parliamentarian", back_populates="candidacies")


__all__ = ["Candidacy"]
