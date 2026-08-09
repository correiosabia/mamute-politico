"""Timeline eleitoral (CS-54) — espelho da API.

Tabela populada pelo tse_crawler; a API apenas le. Sem relationships para nao
acoplar o mapeamento da API ao dos scrappers.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from ..base import Base


class ElectoralHistory(Base):
    __tablename__ = "electoral_history"
    __table_args__ = (
        UniqueConstraint(
            "election_year",
            "tse_candidate_id",
            name="uq_electoral_history_year_tse_id",
        ),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    election_year = Column(Integer, nullable=False, index=True)
    tse_candidate_id = Column(BigInteger, nullable=False)
    tse_election_id = Column(BigInteger)

    parliamentarian_id = Column(
        BigInteger,
        ForeignKey("parliamentarian.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    candidacy_id = Column(
        BigInteger,
        ForeignKey("candidacy.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

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
    assets = Column(JSONB)
    assets_fetched_at = Column(DateTime)

    source_link = Column(Text)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = ["ElectoralHistory"]
