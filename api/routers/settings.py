"""Configurações globais lidas pelo app (não-admin).

A escrita fica em `/admin/settings/*`, atrás do gate de administrador.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

try:
    from ..dependencies import get_db
    from ..services.word_cloud_terms import get_terms
except ImportError:  # execução dentro de api/
    from dependencies import get_db
    from services.word_cloud_terms import get_terms

router = APIRouter(prefix="/settings", tags=["settings"])


class WordCloudTermsOut(BaseModel):
    stopwords: list[str]
    excluded_terms: list[str]


@router.get("/word-cloud-terms", response_model=WordCloudTermsOut)
def read_word_cloud_terms(db: Session = Depends(get_db)) -> dict:
    return get_terms(db)
