"""Estado das feature flags da interface.

O registro de QUAIS flags existem mora no front, em `ui/src/lib/featureFlags.ts`.
Esta tabela guarda apenas em que estado cada uma esta. Linha ausente vale `off`,
e e isso que faz feature nova nascer desligada sem exigir migration por flag.

Linha aqui sem chave correspondente no registro do front e inerte: a tela de
administracao itera sobre o registro, entao a flag removida do codigo some do
controle sozinha, sem precisar de um segundo mecanismo para esconder o botao.

Os tres estados sao deliberadamente poucos: desligado, previa para admins, e
liberado para todos. Nao e sistema de segmentacao — e o ciclo de vida de um
lancamento.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.sql import func

from ..base import Base

STATE_OFF = "off"
STATE_ADMINS = "admins"
STATE_ALL = "all"
VALID_STATES = frozenset({STATE_OFF, STATE_ADMINS, STATE_ALL})

# Modo do vinculo plano x feature (CS-58). Ausencia de linha = oculto.
MODE_LIBERADO = "liberado"
MODE_CADEADO = "cadeado"
VALID_MODES = frozenset({MODE_LIBERADO, MODE_CADEADO})


class FeatureFlag(Base):
    __tablename__ = "feature_flag"
    __table_args__ = (
        # O banco recusa estado invalido mesmo se alguem editar na mao.
        CheckConstraint(
            "state in ('off', 'admins', 'all')",
            name="ck_feature_flag_state",
        ),
    )

    key = Column(Text, primary_key=True)
    state = Column(Text, nullable=False, server_default=STATE_OFF)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class FeatureFlagTier(Base):
    """Vinculo de uma feature com um plano, com modo (CS-58).

    Tabela dedicada, e nao chave dentro de `Tiers.detalhes` (CS-58 pede config
    de recurso x plano no padrao de `word_cloud_terms`). A semantica por plano
    e tri-valorada:

    * sem linha           — oculto: o recurso some da tela;
    * `mode = 'liberado'` — acesso pleno;
    * `mode = 'cadeado'`  — entrada visivel em cinza com cadeado; o conteudo
      carrega como previa truncada e desfocada, com chamada para assinar.

    E da ausencia que sai o comportamento pedido: plano novo, vindo do sync
    do Ghost, nasce sem nenhuma feature, sem ninguem precisar lembrar de
    desligar nada.

    O gate correspondente vale no backend (`api/feature_gate.py`) — desfoque
    no front e vitrine, nao seguranca.
    """

    __tablename__ = "feature_flag_tier"
    __table_args__ = (
        CheckConstraint(
            "mode in ('liberado', 'cadeado')",
            name="ck_feature_flag_tier_mode",
        ),
    )

    flag_key = Column(Text, primary_key=True, index=True)
    tier_id = Column(
        BigInteger,
        ForeignKey("tiers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    mode = Column(Text, nullable=False, server_default=MODE_LIBERADO)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


__all__ = [
    "FeatureFlag",
    "FeatureFlagTier",
    "MODE_CADEADO",
    "MODE_LIBERADO",
    "STATE_ADMINS",
    "STATE_ALL",
    "STATE_OFF",
    "VALID_MODES",
    "VALID_STATES",
]
