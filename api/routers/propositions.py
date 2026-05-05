"""Rotas relacionadas a proposições legislativas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

try:
    # Execução como pacote (api.routers.propositions).
    from ..db.models.proposition import Proposition
    from ..dependencies import get_db
except (ImportError, ValueError):
    # Execução local dentro de api/ sem reconhecimento de pacote.
    from db.models.proposition import Proposition
    from dependencies import get_db

router = APIRouter(prefix="/propositions", tags=["propositions"])
SENADO_PROPOSITION_BASE_URL = "https://www25.senado.leg.br/web/atividade/materias/-/materia"


class PropositionOut(BaseModel):
    """Representação serializada de uma proposição."""

    id: int
    proposition_code: Optional[int] = None
    title: Optional[str] = None
    link: Optional[str] = None
    link_xml: Optional[str] = None
    proposition_acronym: Optional[str] = None
    proposition_number: Optional[int] = None
    presentation_year: Optional[int] = None
    agency_id: Optional[int] = None
    proposition_type_id: Optional[int] = None
    proposition_status_id: Optional[int] = None
    current_status: Optional[str] = None
    proposition_description: Optional[str] = None
    presentation_date: Optional[date] = None
    presentation_month: Optional[int] = None
    summary: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


def _build_proposition_link(proposition: Proposition) -> Optional[str]:
    # TODO: Implementar a logica do link na fonte ao inves do codigo abaixo
    if isinstance(proposition.link, str) and "camara.leg.br" in proposition.link:
        # Proposições da Câmara (deputados) devem apontar para a ficha de tramitação.
        return proposition.link
    if proposition.proposition_code is not None:
        return f"{SENADO_PROPOSITION_BASE_URL}/{proposition.proposition_code}"
    if isinstance(proposition.link, str) and proposition.link:
        return proposition.link
    return None


def _serialize_proposition(proposition: Proposition) -> PropositionOut:
    computed_link = _build_proposition_link(proposition)
    return PropositionOut(
        id=proposition.id,
        proposition_code=proposition.proposition_code,
        title=proposition.title,
        link=computed_link,
        link_xml=proposition.link,
        proposition_acronym=proposition.proposition_acronym,
        proposition_number=proposition.proposition_number,
        presentation_year=proposition.presentation_year,
        agency_id=proposition.agency_id,
        proposition_type_id=proposition.proposition_type_id,
        proposition_status_id=proposition.proposition_status_id,
        current_status=proposition.current_status,
        proposition_description=proposition.proposition_description,
        presentation_date=proposition.presentation_date,
        presentation_month=proposition.presentation_month,
        summary=proposition.summary,
        details=proposition.details,
        created_at=proposition.created_at,
        updated_at=proposition.updated_at,
    )


@router.get("/", response_model=List[PropositionOut])
def list_propositions(
    *,
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    year: Optional[int] = Query(None, description="Filtra pelo ano de apresentação."),
    acronym: Optional[str] = Query(
        None, description="Filtra pela sigla da proposição (ex: PEC, PL, etc)."
    ),
    presentation_date_from: Optional[date] = Query(
        None,
        description="Filtra por data de apresentação a partir desta data (inclusive).",
    ),
    presentation_date_to: Optional[date] = Query(
        None,
        description="Filtra por data de apresentação até esta data (inclusive).",
    ),
    created_from: Optional[datetime] = Query(
        None,
        description="Filtra por registros criados a partir deste instante (inclusive).",
    ),
    created_to: Optional[datetime] = Query(
        None,
        description="Filtra por registros criados até este instante (inclusive).",
    ),
    updated_from: Optional[datetime] = Query(
        None,
        description="Filtra por registros atualizados a partir deste instante (inclusive).",
    ),
    updated_to: Optional[datetime] = Query(
        None,
        description="Filtra por registros atualizados até este instante (inclusive).",
    ),
    sort_by: Literal[
        "created_at",
        "updated_at",
        "title",
        "presentation_date",
        "presentation_year",
        "proposition_number",
    ] = Query(default="created_at", description="Campo usado para ordenação."),
    sort_order: Literal["asc", "desc"] = Query(
        default="desc",
        description="Direção da ordenação.",
    ),
) -> List[PropositionOut]:
    """Retorna uma lista paginada de proposições."""
    stmt = select(Proposition).offset(offset).limit(limit)

    if year is not None:
        stmt = stmt.where(Proposition.presentation_year == year)
    if acronym:
        stmt = stmt.where(Proposition.proposition_acronym.ilike(f"%{acronym}%"))
    if presentation_date_from is not None:
        stmt = stmt.where(Proposition.presentation_date >= presentation_date_from)
    if presentation_date_to is not None:
        stmt = stmt.where(Proposition.presentation_date <= presentation_date_to)
    if created_from is not None:
        stmt = stmt.where(Proposition.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(Proposition.created_at <= created_to)
    if updated_from is not None:
        stmt = stmt.where(Proposition.updated_at >= updated_from)
    if updated_to is not None:
        stmt = stmt.where(Proposition.updated_at <= updated_to)

    sortable_columns = {
        "created_at": Proposition.created_at,
        "updated_at": Proposition.updated_at,
        "title": Proposition.title,
        "presentation_date": Proposition.presentation_date,
        "presentation_year": Proposition.presentation_year,
        "proposition_number": Proposition.proposition_number,
    }
    sort_column = sortable_columns[sort_by]
    stmt = stmt.order_by(asc(sort_column) if sort_order == "asc" else desc(sort_column))

    result = db.execute(stmt)
    propositions = result.scalars().all()
    return [_serialize_proposition(proposition) for proposition in propositions]


@router.get("/{proposition_id}", response_model=PropositionOut)
def get_proposition(
    proposition_id: int,
    db: Session = Depends(get_db),
) -> PropositionOut:
    """Recupera detalhes de uma proposição específica."""
    stmt = select(Proposition).where(Proposition.id == proposition_id)
    result = db.execute(stmt).scalar_one_or_none()

    if result is None:
        raise HTTPException(status_code=404, detail="Proposição não encontrada.")

    return _serialize_proposition(result)


__all__ = ["router"]

