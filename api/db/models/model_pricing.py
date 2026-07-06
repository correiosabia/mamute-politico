"""Preço por modelo de LLM (US$ por 1M tokens), sincronizável do OpenRouter."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Numeric, Text, UniqueConstraint
from sqlalchemy.sql import func

from ..base import Base


class ModelPricing(Base):
    __tablename__ = "model_pricing"
    __table_args__ = (UniqueConstraint("model", name="uq_model_pricing_model"),)

    id = Column(BigInteger, primary_key=True, index=True)
    model = Column(Text, nullable=False)
    input_usd_per_1m = Column(Numeric(12, 6), nullable=False, server_default="0")
    output_usd_per_1m = Column(Numeric(12, 6), nullable=False, server_default="0")
    currency = Column(Text, nullable=False, server_default="USD")
    source = Column(Text, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = ["ModelPricing"]
