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
    Date,
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
    # A UF integra a chave natural por causa de 2002/2006: nesses anos o
    # SQ_CANDIDATO dos dados abertos e sequencial POR UF (o "119" existe em 26
    # estados). De 2010 em diante o id e global e a UF na chave e inocua.
    __table_args__ = (
        UniqueConstraint(
            "election_year",
            "state",
            "tse_candidate_id",
            name="uq_candidacy_election_state_tse_id",
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

    # Perfil demografico (CS-63). Valores normalizados em MAIUSCULAS na forma
    # dos CSVs de dados abertos do TSE, para agregacao cruzada entre fontes
    # (a DivulgaCandContas devolve "MASC."/"Superior completo"; o CSV,
    # "MASCULINO"/"SUPERIOR COMPLETO"). Cor/raca so existe a partir de 2014 e
    # federacao a partir de 2022 — NULL antes disso e lacuna da fonte, nao bug.
    birth_date = Column(Date)
    gender = Column(Text)
    race = Column(Text)
    education = Column(Text)
    occupation = Column(Text)
    marital_status = Column(Text)
    nationality = Column(Text)
    federation = Column(Text)
    # 'divulgacand' (detalhe da API) ou 'tse_csv' (dados abertos). O CSV nunca
    # sobrescreve campo preenchido pela API; so completa NULL.
    profile_source = Column(Text)

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

    electoral_history = relationship(
        "ElectoralHistory",
        back_populates="candidacy",
    )


__all__ = ["Candidacy"]
