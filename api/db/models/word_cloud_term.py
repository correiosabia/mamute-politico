"""Termos filtrados da nuvem de palavras, geridos pelo painel admin.

Dois tipos, com efeitos deliberadamente diferentes:

* `stopword` — removida palavra a palavra de dentro de uma expressão.
  "o projeto de lei" vira "lei".
* `excluded` — descarta a entrada inteira quando ela bate por completo.
  "mudança climática" some da nuvem.

A distinção importa: um termo ambíguo como "união" (sigla de partido, mas também
palavra comum) precisa ser `excluded`. Como `stopword` ele mutilaria expressões
legítimas — "união estável" viraria "estável".
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Text, UniqueConstraint
from sqlalchemy.sql import func

from ..base import Base

KIND_STOPWORD = "stopword"
KIND_EXCLUDED = "excluded"


class WordCloudTerm(Base):
    __tablename__ = "word_cloud_terms"
    __table_args__ = (
        # Dedupe garantida pelo banco, não só pela aplicação.
        UniqueConstraint("term", "kind", name="uq_word_cloud_terms_term_kind"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    term = Column(Text, nullable=False)
    kind = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
