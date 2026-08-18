"""Leitura e escrita do estado das feature flags.

O registro de quais flags existem mora no front (`ui/src/lib/featureFlags.ts`).
Aqui so ha estado e a regra que traduz tri-estado + modo do plano no valor
resolvido de quem chamou ('liberada' | 'bloqueada' | 'oculta').
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

try:
    from ..db.models.feature_flag import (
        MODE_CADEADO,
        MODE_LIBERADO,
        STATE_ALL,
        STATE_OFF,
        VALID_MODES,
        VALID_STATES,
        FeatureFlag,
        FeatureFlagTier,
    )
except ImportError:  # execução dentro de api/
    from db.models.feature_flag import (
        MODE_CADEADO,
        MODE_LIBERADO,
        STATE_ALL,
        STATE_OFF,
        VALID_MODES,
        VALID_STATES,
        FeatureFlag,
        FeatureFlagTier,
    )

# Valores resolvidos para quem chamou (CS-58). 'bloqueada' e o cadeado com
# previa desfocada: a entrada aparece, o dado completo nao.
ACCESS_LIBERADA = "liberada"
ACCESS_BLOQUEADA = "bloqueada"
ACCESS_OCULTA = "oculta"


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
    modos: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Aplica o tri-estado e o modo do plano a quem chamou.

    A divisao de responsabilidade e deliberada:

    * o tri-estado (`off`/`admins`/`all`) e o ciclo de vida do lancamento, e
      vive em `/admin/configuracoes`;
    * o modo por plano (`liberado`/`cadeado`/ausente) vive na tela de tiers,
      junto das demais quantidades e limites do plano.

    Por isso `all` nao significa "todo mundo ve": significa "o lancamento
    terminou, agora quem decide e o plano". E cadeado so existe em `all` —
    recurso ainda em previa (`admins`) nao vira vitrine para nao-admin.

    Admin resolve `liberada` para tudo que nao esta `off`, independente do
    plano dele: o papel de admin e previa e conferencia, nao assinatura.

    Devolve o valor ja resolvido ('liberada' | 'bloqueada' | 'oculta'), e nao
    o estado cru, para o front nao repetir esta regra — e para os call sites
    de `useFeatureFlag`/`useFeatureAccess` serem os menores possiveis, que e
    o que torna a remocao da flag barata.
    """
    do_plano = dict(modos or {})

    resolvido: dict[str, str] = {}
    for key, state in get_states(db).items():
        if is_admin:
            resolvido[key] = (
                ACCESS_OCULTA if state == STATE_OFF else ACCESS_LIBERADA
            )
        elif state == STATE_ALL and do_plano.get(key) == MODE_LIBERADO:
            resolvido[key] = ACCESS_LIBERADA
        elif state == STATE_ALL and do_plano.get(key) == MODE_CADEADO:
            resolvido[key] = ACCESS_BLOQUEADA
        else:
            resolvido[key] = ACCESS_OCULTA
    return resolvido


def enabled_flags_for_tier(db: Session, tier_id: int | None) -> dict[str, str]:
    """Modo de cada feature no plano (chave -> 'liberado' | 'cadeado').

    Vive em tabela dedicada (`feature_flag_tier`), e nao em `Tiers.detalhes`:
    a CS-58 pede config de recurso x plano no padrao de `word_cloud_terms`.
    Chave ausente = oculto no plano — e por isso que plano novo, vindo do
    sync do Ghost, nasce sem nenhuma feature.
    """
    if tier_id is None:
        return {}

    linhas = db.execute(
        select(FeatureFlagTier.flag_key, FeatureFlagTier.mode).where(
            FeatureFlagTier.tier_id == tier_id
        )
    ).all()
    return {key: mode for key, mode in linhas}


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


def count_tiers_enabled(db: Session) -> dict[str, dict[str, int]]:
    """Quantos planos ativos tem cada feature, por modo.

    Devolve `{chave: {"liberado": n, "cadeado": n}}` (modo sem linha nao
    aparece). Serve para a tela de administracao denunciar o caso silencioso:
    flag em `all` sem nenhum plano nao aparece para ninguem.
    """
    try:
        from ..db.models.project import Tiers
    except ImportError:  # execução dentro de api/
        from db.models.project import Tiers

    linhas = db.execute(
        select(
            FeatureFlagTier.flag_key,
            FeatureFlagTier.mode,
            func.count(FeatureFlagTier.tier_id),
        )
        .join(Tiers, Tiers.id == FeatureFlagTier.tier_id)
        .where(Tiers.deleted_at.is_(None))
        .group_by(FeatureFlagTier.flag_key, FeatureFlagTier.mode)
    ).all()
    contagem: dict[str, dict[str, int]] = {}
    for key, mode, total in linhas:
        contagem.setdefault(key, {})[mode] = total
    return contagem


def set_tier_flags(
    db: Session, tier_id: int, modos: Mapping[str, str]
) -> dict[str, str]:
    """Substitui por completo o mapa feature -> modo de um plano.

    Substituir espelha a intencao da tela, que edita o mapa inteiro do plano
    e salva de uma vez — mesma politica de `word_cloud_terms.replace_terms`.
    Nao commita: quem chama decide o momento, para a auditoria entrar na mesma
    transacao.
    """
    desejadas = {str(k): str(v) for k, v in (modos or {}).items()}
    invalidos = set(desejadas.values()) - VALID_MODES
    if invalidos:
        raise ValueError(f"modo invalido: {sorted(invalidos)!r}")

    atuais = {
        linha.flag_key: linha
        for linha in db.execute(
            select(FeatureFlagTier).where(FeatureFlagTier.tier_id == tier_id)
        ).scalars()
    }

    for key, linha in atuais.items():
        if key not in desejadas:
            db.delete(linha)
        elif linha.mode != desejadas[key]:
            linha.mode = desejadas[key]
    for key in set(desejadas) - set(atuais):
        db.add(
            FeatureFlagTier(flag_key=key, tier_id=tier_id, mode=desejadas[key])
        )
    db.flush()

    return dict(sorted(desejadas.items()))


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
