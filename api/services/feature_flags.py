"""Leitura e escrita do estado das feature flags.

O registro de quais flags existem mora no front (`ui/src/lib/featureFlags.ts`).
Aqui so ha estado e a regra que traduz o tri-estado em booleano.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    from ..db.models.feature_flag import (
        STATE_ADMINS,
        STATE_ALL,
        VALID_STATES,
        FeatureFlag,
    )
except ImportError:  # execução dentro de api/
    from db.models.feature_flag import (
        STATE_ADMINS,
        STATE_ALL,
        VALID_STATES,
        FeatureFlag,
    )


def get_states(db: Session) -> dict[str, str]:
    """Tri-estado cru de cada linha gravada.

    Chave sem linha simplesmente nao aparece: quem le trata a ausencia como
    `off`. Inventar a chave aqui exigiria o backend conhecer o registro do
    front, que e justamente o acoplamento que este desenho evita.
    """
    linhas = db.execute(select(FeatureFlag.key, FeatureFlag.state)).all()
    return {key: state for key, state in linhas}


def resolve_for(db: Session, is_admin: bool) -> dict[str, bool]:
    """Aplica o tri-estado a quem chamou.

    Devolve booleano, e nao o estado cru, para o front nao repetir esta regra
    — e para o call site do `useFeatureFlag` ser o mais simples possivel, que
    e o que torna a remocao da flag barata.
    """
    return {
        key: state == STATE_ALL or (state == STATE_ADMINS and is_admin)
        for key, state in get_states(db).items()
    }


def set_state(db: Session, key: str, state: str) -> dict:
    """Grava o estado da flag. Nao commita: quem chama decide o momento,
    para a linha de auditoria entrar na mesma transacao.
    """
    if state not in VALID_STATES:
        raise ValueError(f"estado invalido: {state!r}")

    linha = db.get(FeatureFlag, key)
    if linha is None:
        linha = FeatureFlag(key=key, state=state)
        db.add(linha)
    else:
        linha.state = state
    linha.updated_at = datetime.now(timezone.utc)
    db.flush()

    return {
        "key": linha.key,
        "state": linha.state,
        "updated_at": linha.updated_at,
    }
