"""Plano de acao de emenda Pix (transferencia especial), do Transferegov.

Uma emenda Pix se desdobra em varios planos de acao, um por ente beneficiario
— mediana de 8, maximo medido 100, 57.827 planos na fonte. Por isso a relacao
com `parliamentary_amendment` e 1:N, e nao 1:1.

A prestacao de contas vem desnormalizada: a fonte tem 1,02 relatorio por plano
(1.725 relatorios para 1.685 planos), entao guardar o mais forte basta. A regra
de precedencia esta em `transferegov_crawler.action_plans.escolher_relatorio`.
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
)
from sqlalchemy.sql import func

from ..base import Base


class AmendmentActionPlan(Base):
    __tablename__ = "amendment_action_plan"

    # Chave natural da fonte: o upsert casa por ela.
    id_plano_acao = Column(BigInteger, primary_key=True)
    codigo_plano_acao = Column(Text)

    # SET NULL como em parliamentary_amendment.parliamentarian_id: o plano de
    # acao e fato publico e nao deve sumir se a emenda sair da base.
    amendment_code = Column(
        Text,
        ForeignKey("parliamentary_amendment.amendment_code", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    ano = Column(Integer, index=True)
    situacao = Column(Text)

    beneficiario_nome = Column(Text)
    beneficiario_cnpj = Column(Text)
    beneficiario_uf = Column(Text)

    valor_custeio = Column(Numeric(18, 2))
    valor_investimento = Column(Numeric(18, 2))

    prestacao_situacao = Column(Text)
    prestacao_tipo = Column(Text)
    prestacao_valor_executado = Column(Numeric(18, 2))
    prestacao_valor_pendente = Column(Numeric(18, 2))
    prestacao_data = Column(Text)
    prestacao_origem = Column(Text)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = ["AmendmentActionPlan"]
