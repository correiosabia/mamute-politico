"""Configurações globais lidas pelo app (não-admin).

A escrita fica em `/admin/settings/*`, atrás do gate de administrador.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

try:
    from ..dependencies import get_db
    from ..security import resolve_ghost_admin
    from ..services.feature_flags import resolve_for
    from ..services.word_cloud_terms import get_terms
except ImportError:  # execução dentro de api/
    from dependencies import get_db
    from security import resolve_ghost_admin
    from services.feature_flags import resolve_for
    from services.word_cloud_terms import get_terms

router = APIRouter(prefix="/settings", tags=["settings"])


class WordCloudTermsOut(BaseModel):
    stopwords: list[str]
    excluded_terms: list[str]


@router.get("/word-cloud-terms", response_model=WordCloudTermsOut)
def read_word_cloud_terms(db: Session = Depends(get_db)) -> dict:
    return get_terms(db)


@router.get("/feature-flags")
def read_feature_flags(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """Estado das flags já resolvido para quem chamou.

    Devolve booleano e não o tri-estado: quem não é admin não precisa saber
    que a flag existe em modo `admins`, e o front não repete a regra.

    Isto controla apenas a exibição na interface. Os endpoints de dado seguem
    abertos — não é fronteira de segurança.
    """
    is_admin = resolve_ghost_admin(request, authorization) is not None
    return resolve_for(db, is_admin=is_admin)
