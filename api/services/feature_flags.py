"""Leitura e escrita do estado das feature flags.

O registro de quais flags existem mora no front (`ui/src/lib/featureFlags.ts`).
Aqui so ha estado e a regra que traduz o tri-estado em booleano.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

try:
    from ..db.models.feature_flag import (
        STATE_ADMINS,
        STATE_ALL,
        VALID_STATES,
        FeatureFlag,
        FeatureFlagTier,
    )
except ImportError:  # execução dentro de api/
    from db.models.feature_flag import (
        STATE_ADMINS,
        STATE_ALL,
        VALID_STATES,
        FeatureFlag,
        FeatureFlagTier,
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
    liberadas: Iterable[str] | None = None,
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
    do_plano = set(liberadas or ())

    resolvido: dict[str, bool] = {}
    for key, state in get_states(db).items():
        if state == STATE_ALL:
            resolvido[key] = is_admin or key in do_plano
        elif state == STATE_ADMINS:
            resolvido[key] = is_admin
        else:
            resolvido[key] = False
    return resolvido


def enabled_flags_for_tier(db: Session, tier_id: int | None) -> set[str]:
    """Chaves liberadas para um plano.

    Vive em tabela dedicada (`feature_flag_tier`), e nao em `Tiers.detalhes`:
    a CS-58 pede config de recurso x plano no padrao de `word_cloud_terms`.
    Linha presente = liberado; ausencia = nao liberado.

    PONTO DE EXTENSAO — hoje "nao liberado" significa "omitir da tela". A
    CS-58 preve o modo "cadeado com previa desfocada", que AINDA NAO EXISTE.
    Quando chegar, a tabela ganha coluna de modo e esta funcao passa a devolver
    o modo em vez de um conjunto; alem disso o gate tera de valer no backend,
    porque desfoque no front e vitrine, nao seguranca.
    """
    if tier_id is None:
        return set()

    linhas = db.execute(
        select(FeatureFlagTier.flag_key).where(FeatureFlagTier.tier_id == tier_id)
    ).scalars()
    return set(linhas)


def tier_id_for_email(db: Session, email: str | None) -> int | None:
    """Plano do e-mail autenticado, ou `None`.

    Versao suave de `_get_project_from_token_email` (routers/projects.py), que
    levanta 404 quando nao acha: aqui, nao achar projeto ou tier vale "sem
    plano" e o usuario nao ve feature restrita a plano. Falha fechado, sem
    erro na tela.

    Na pratica e caso raro — o Mamute so libera a interface a partir do plano
    basico —, mas vinculo quebrado nao pode virar 500 numa chamada que so
    decide o que renderizar.
    """
    if not email:
        return None

    try:
        from ..db.models.project import Projetos
    except ImportError:  # execução dentro de api/
        from db.models.project import Projetos

    return db.execute(
        select(Projetos.tier_id).where(
            Projetos.email == email,
            Projetos.deleted_at.is_(None),
        )
    ).scalars().first()


def count_tiers_enabled(db: Session) -> dict[str, int]:
    """Quantos planos ativos tem cada feature liberada.

    Serve para a tela de administracao denunciar o caso silencioso: flag em
    `all` com zero planos liberados nao aparece para ninguem.
    """
    try:
        from ..db.models.project import Tiers
    except ImportError:  # execução dentro de api/
        from db.models.project import Tiers

    linhas = db.execute(
        select(FeatureFlagTier.flag_key, func.count(FeatureFlagTier.tier_id))
        .join(Tiers, Tiers.id == FeatureFlagTier.tier_id)
        .where(Tiers.deleted_at.is_(None))
        .group_by(FeatureFlagTier.flag_key)
    ).all()
    return {key: total for key, total in linhas}


def set_tier_flags(db: Session, tier_id: int, keys: Iterable[str]) -> list[str]:
    """Substitui por completo as features liberadas de um plano.

    Substituir espelha a intencao da tela, que edita a lista inteira do plano
    e salva de uma vez — mesma politica de `word_cloud_terms.replace_terms`.
    Nao commita: quem chama decide o momento, para a auditoria entrar na mesma
    transacao.
    """
    desejadas = {str(k) for k in keys or []}

    atuais = {
        linha.flag_key: linha
        for linha in db.execute(
            select(FeatureFlagTier).where(FeatureFlagTier.tier_id == tier_id)
        ).scalars()
    }

    for key, linha in atuais.items():
        if key not in desejadas:
            db.delete(linha)
    for key in desejadas - set(atuais):
        db.add(FeatureFlagTier(flag_key=key, tier_id=tier_id))
    db.flush()

    return sorted(desejadas)


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
