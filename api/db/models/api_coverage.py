"""Contagens das APIs abertas (Câmara/Senado) para comparar cobertura do banco."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Integer, Text, UniqueConstraint
from sqlalchemy.sql import func

from ..base import Base


class ApiCoverage(Base):
    __tablename__ = "api_coverage"
    __table_args__ = (
        UniqueConstraint("source", "year", "sigla_type", name="uq_api_coverage_key"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    source = Column(Text, nullable=False)  # camara | senado
    year = Column(Integer, nullable=False)
    sigla_type = Column(Text, nullable=True)
    api_count = Column(Integer, nullable=False, server_default="0")
    synced_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


__all__ = ["ApiCoverage"]
