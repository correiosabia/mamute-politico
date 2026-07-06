"""Uso mensal do chatbot por projeto."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


class ChatbotUsage(Base):
    __tablename__ = "chatbot_usage"
    __table_args__ = (
        Index("ix_chatbot_usage_projeto_period", "projeto_id", "period_start"),
        Index("ix_chatbot_usage_email_period", "email", "period_start"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    projeto_id = Column(
        BigInteger,
        ForeignKey("projetos.id", ondelete="CASCADE"),
        nullable=False,
    )
    email = Column(Text, nullable=False)
    request_id = Column(Text, nullable=False, unique=True)
    period_start = Column(Date, nullable=False)
    status = Column(Text, nullable=False, index=True)
    question_chars = Column(Integer, nullable=False, server_default="0")
    answer_chars = Column(Integer, nullable=False, server_default="0")
    model = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    cost_usd = Column(Numeric(12, 6), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    projeto = relationship("Projetos")


__all__ = ["ChatbotUsage"]
