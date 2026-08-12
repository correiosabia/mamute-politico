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

from sqlalchemy import CheckConstraint, Column, DateTime, Text
from sqlalchemy.sql import func

from ..base import Base

STATE_OFF = "off"
STATE_ADMINS = "admins"
STATE_ALL = "all"
VALID_STATES = frozenset({STATE_OFF, STATE_ADMINS, STATE_ALL})


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


__all__ = [
    "FeatureFlag",
    "STATE_ADMINS",
    "STATE_ALL",
    "STATE_OFF",
    "VALID_STATES",
]
