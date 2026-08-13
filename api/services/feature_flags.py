"""Leitura e escrita do estado das feature flags.

O registro de quais flags existem mora no front (`ui/src/lib/featureFlags.ts`).
Aqui so ha estado e a regra que traduz o tri-estado em booleano.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

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


def resolve_for(
    db: Session,
    is_admin: bool,
    tier_features: Mapping[str, bool] | None = None,
) -> dict[str, bool]:
    """Aplica o tri-estado e o recorte por plano a quem chamou.

    A divisao de responsabilidade e deliberada:

    * o tri-estado (`off`/`admins`/`all`) e o ciclo de vida do lancamento, e
      vive em `/admin/configuracoes`;
    * o recorte por plano vive na tela de tiers, junto das demais quantidades
      e limites do plano.

    Por isso `all` nao significa "todo mundo ve": significa "o lancamento
    terminou, agora quem decide e o plano". Plano sem a chave ligada nao ve —
    e por isso que plano novo, vindo do sync do Ghost, nasce sem a feature.

    Admin ve tudo que nao esta `off`, independente do plano dele: o papel de
    admin e previa e conferencia, nao assinatura.

    Devolve booleano, e nao o estado cru, para o front nao repetir esta regra
    — e para o call site do `useFeatureFlag` ser o mais simples possivel, que
    e o que torna a remocao da flag barata.
    """
    liberado = tier_features or {}

    resolvido: dict[str, bool] = {}
    for key, state in get_states(db).items():
        if state == STATE_ALL:
            resolvido[key] = is_admin or liberado.get(key) is True
        elif state == STATE_ADMINS:
            resolvido[key] = is_admin
        else:
            resolvido[key] = False
    return resolvido


def tier_features_of(tier: Any) -> dict[str, bool]:
    """Chaves de feature ligadas num tier.

    Moram em `detalhes["features"]`, ao lado das quantidades do plano
    (`qtd_termos` e afins) — a tela de tiers ja e o lugar onde se configura o
    que cada plano da. Chave ausente vale desligado.

    PONTO DE EXTENSAO — feature desligada hoje significa "omitir da tela". Esta
    previsto um segundo comportamento, "cadeado com blur" (mostrar bloqueado,
    como chamariz de upgrade), que AINDA NAO EXISTE e nao foi construido aqui.

    Quando ele chegar, o valor guardado deixa de ser booleano e vira enum de
    string ("on" | "off" | "locked"). Como `detalhes` e JSONB, isso nao exige
    migration: basta widen deste parser (valor ausente ou False continua
    "off") e um `useFeatureAccess` no front, ao lado do `useFeatureFlag`, para
    quem precisa distinguir omitido de bloqueado. O `useFeatureFlag` booleano
    continua valido — "posso usar?" e uma pergunta que sobrevive aos tres
    modos.
    """
    if tier is None:
        return {}
    detalhes = getattr(tier, "detalhes", None) or {}
    features = detalhes.get("features") if isinstance(detalhes, dict) else None
    if not isinstance(features, dict):
        return {}
    return {str(k): v is True for k, v in features.items()}


def tier_features_for_email(db: Session, email: str | None) -> dict[str, bool]:
    """Features liberadas para o plano do e-mail autenticado.

    Versao suave de `_get_project_from_token_email` (routers/projects.py), que
    levanta 404 quando nao acha: aqui, nao achar projeto ou tier vale "sem
    plano" e o usuario simplesmente nao ve feature restrita a plano. Falha
    fechado, sem erro na tela.

    Na pratica e caso raro — o Mamute so libera a interface a partir do plano
    basico —, mas vinculo quebrado nao pode virar 500 numa chamada que so
    decide o que renderizar.
    """
    if not email:
        return {}

    try:
        from ..db.models.project import Projetos, Tiers
    except ImportError:  # execução dentro de api/
        from db.models.project import Projetos, Tiers

    stmt = (
        select(Tiers)
        .join(Projetos, Projetos.tier_id == Tiers.id)
        .where(
            Projetos.email == email,
            Projetos.deleted_at.is_(None),
            Tiers.deleted_at.is_(None),
        )
    )
    return tier_features_of(db.execute(stmt).scalars().first())


def count_tiers_enabled(db: Session) -> dict[str, int]:
    """Quantos planos ativos tem cada feature ligada.

    Serve para a tela de administracao denunciar o caso silencioso: flag em
    `all` com zero planos ligados nao aparece para ninguem.
    """
    try:
        from ..db.models.project import Tiers
    except ImportError:  # execução dentro de api/
        from db.models.project import Tiers

    contagem: dict[str, int] = {}
    tiers = db.execute(select(Tiers).where(Tiers.deleted_at.is_(None))).scalars()
    for tier in tiers:
        for key, ligado in tier_features_of(tier).items():
            if ligado:
                contagem[key] = contagem.get(key, 0) + 1
    return contagem


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
