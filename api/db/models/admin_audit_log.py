"""Log de auditoria de ações administrativas (escritas de config)."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Text
from sqlalchemy.sql import func

from ..base import Base


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id = Column(BigInteger, primary_key=True, index=True)
    admin_email = Column(Text, nullable=False)
    action = Column(Text, nullable=False)
    entity = Column(Text, nullable=False)
    entity_id = Column(Text, nullable=True)
    before = Column(Text, nullable=True)  # JSON serializado
    after = Column(Text, nullable=True)  # JSON serializado
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
