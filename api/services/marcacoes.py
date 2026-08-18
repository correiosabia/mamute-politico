from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    from ..db.models.marcacoes_config import (
        ESCOPO_MONITORADOS,
        ESCOPO_TODOS,
        ESCOPOS_VALIDOS,
        LINHA_UNICA_ID,
        MAX_LEVEL_MAXIMO,
        MAX_LEVEL_MINIMO,
        MAX_LEVEL_PADRAO,
        NOTICE_PADRAO,
        MarcacoesConfig,
    )
    from ..db.models.personal_marks import ProjectMamutometro
    from ..db.models.project import ProjetosParliamentarian
    from .feature_flags import ACCESS_LIBERADA, enabled_flags_for_tier, resolve_for
except ImportError:  # execução dentro de api/
    from db.models.marcacoes_config import (
        ESCOPO_MONITORADOS,
        ESCOPO_TODOS,
        ESCOPOS_VALIDOS,
        LINHA_UNICA_ID,
        MAX_LEVEL_MAXIMO,
        MAX_LEVEL_MINIMO,
        MAX_LEVEL_PADRAO,
        NOTICE_PADRAO,
        MarcacoesConfig,
    )
    from db.models.personal_marks import ProjectMamutometro
    from db.models.project import ProjetosParliamentarian
    from services.feature_flags import ACCESS_LIBERADA, enabled_flags_for_tier, resolve_for

FLAG_MAMUTOMETRO = "mamutometro"
CAMPO_LIMITE_TIER = "qtd_mamutometro"


def get_config(db: Session) -> MarcacoesConfig:
    """Configuração vigente, com padrões de fábrica se a linha não existir.

    A migration insere a linha, mas devolver um objeto transiente quando ela
    falta evita que um banco meio-migrado derrube a tela — e mantém os testes
    livres de fixture obrigatória.
    """
    linha = db.get(MarcacoesConfig, LINHA_UNICA_ID)
    if linha is not None:
        return linha
    return MarcacoesConfig(
        id=LINHA_UNICA_ID,
        mamutometro_max_level=MAX_LEVEL_PADRAO,
        mamutometro_notice_text=NOTICE_PADRAO,
        mamutometro_escopo=ESCOPO_MONITORADOS,
        tags_escopo=ESCOPO_TODOS,
    )


def set_config(
    db: Session,
    *,
    mamutometro_max_level: int,
    mamutometro_notice_text: str,
    mamutometro_escopo: str,
    tags_escopo: str,
) -> MarcacoesConfig:
    """Grava a configuração. Não commita — quem chama decide o momento, para a
    linha de auditoria entrar na mesma transação (mesma política de
    `feature_flags.set_state`).
    """
    nivel = int(mamutometro_max_level)
    if not MAX_LEVEL_MINIMO <= nivel <= MAX_LEVEL_MAXIMO:
        raise ValueError(
            f"o total de mamutes deve ficar entre {MAX_LEVEL_MINIMO} e {MAX_LEVEL_MAXIMO}"
        )
    for nome, valor in (
        ("mamutometro_escopo", mamutometro_escopo),
        ("tags_escopo", tags_escopo),
    ):
        if valor not in ESCOPOS_VALIDOS:
            raise ValueError(f"{nome} inválido: {valor!r}")
    texto = (mamutometro_notice_text or "").strip()
    if not texto:
        raise ValueError("o texto do aviso não pode ficar vazio")
    linha = db.get(MarcacoesConfig, LINHA_UNICA_ID)
    if linha is None:
        linha = MarcacoesConfig(id=LINHA_UNICA_ID)
        db.add(linha)
    linha.mamutometro_max_level = nivel
    linha.mamutometro_notice_text = texto
    linha.mamutometro_escopo = mamutometro_escopo
    linha.tags_escopo = tags_escopo
    db.flush()
    return linha


def mamutometro_habilitado(db: Session, project: Any, *, is_admin: bool = False) -> bool:

    modos = enabled_flags_for_tier(db, getattr(project, "tier_id", None))
    resolvido = resolve_for(db, is_admin=is_admin, modos=modos)
    # So acesso pleno habilita a escrita: cadeado e vitrine, nao permissao.
    return resolvido.get(FLAG_MAMUTOMETRO) == ACCESS_LIBERADA


def mamutometro_limite(project: Any) -> Optional[int]:

    try:
        from ..routers.projects import _tier_limit_from_db, _tier_limit_from_env
    except ImportError:  # execução dentro de api/
        from routers.projects import _tier_limit_from_db, _tier_limit_from_env
    limite = _tier_limit_from_env(project, CAMPO_LIMITE_TIER)
    if limite is not None:
        return limite
    return _tier_limit_from_db(project, CAMPO_LIMITE_TIER)


def mamutometro_usados(db: Session, project_id: int) -> int:
    from sqlalchemy import func
    return int(
        db.execute(
            select(func.count())
            .select_from(ProjectMamutometro)
            .where(ProjectMamutometro.projeto_id == project_id)
        ).scalar_one()
    )


def esta_no_escopo(
    db: Session, project_id: int, parliamentarian_id: int, escopo: str
) -> bool:
    if escopo == ESCOPO_TODOS:
        return True
    return (
        db.execute(
            select(ProjetosParliamentarian.id).where(
                ProjetosParliamentarian.projeto_id == project_id,
                ProjetosParliamentarian.parliamentarian_id == parliamentarian_id,
            )
        ).first()
        is not None
    )


__all__ = [
    "FLAG_MAMUTOMETRO",
    "CAMPO_LIMITE_TIER",
    "get_config",
    "set_config",
    "mamutometro_habilitado",
    "mamutometro_limite",
    "mamutometro_usados",
    "esta_no_escopo",
]
