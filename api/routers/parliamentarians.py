"""Rotas relacionadas a parlamentares."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, asc, desc, or_, select
from sqlalchemy.orm import Session, selectinload

try:
    # Execução como pacote (api.routers.parliamentarians).
    from ..db.models.parliamentarian import Parliamentarian
    from ..db.models.social_network import ParliamentarianSocialNetwork
    from ..dependencies import get_db
except (ImportError, ValueError):
    # Execução local dentro de api/ sem reconhecimento de pacote.
    from db.models.parliamentarian import Parliamentarian
    from db.models.social_network import ParliamentarianSocialNetwork
    from dependencies import get_db

router = APIRouter(prefix="/parliamentarians", tags=["parliamentarians"])


class ParliamentarianOut(BaseModel):
    """Representação serializada de um parlamentar."""

    id: int
    type: Optional[str] = None
    parliamentarian_code: Optional[int] = None
    name: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    telephone: Optional[str] = None
    cpf: Optional[str] = None
    status: Optional[str] = None
    party: Optional[str] = None
    state_of_birth: Optional[str] = None
    city_of_birth: Optional[str] = None
    state_elected: Optional[str] = None
    site: Optional[str] = None
    education: Optional[str] = None
    office_name: Optional[str] = None
    office_building: Optional[str] = None
    office_number: Optional[str] = None
    office_floor: Optional[str] = None
    office_email: Optional[str] = None
    biography_link: Optional[str] = None
    biography_text: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SocialNetworkLinkOut(BaseModel):
    """Rede social vinculada a um parlamentar."""

    name: Optional[str] = None
    profile_url: Optional[str] = None


class ParliamentarianDetailOut(ParliamentarianOut):
    """Representação detalhada de um parlamentar, incluindo redes sociais."""

    social_networks: List[SocialNetworkLinkOut] = Field(default_factory=list)


def _serialize_parliamentarian_detail(parliamentarian: Parliamentarian) -> ParliamentarianDetailOut:
    """Serializa um parlamentar com suas redes sociais."""
    base = ParliamentarianOut.model_validate(parliamentarian)
    social_networks = [
        SocialNetworkLinkOut(
            name=link.social_network.name if link.social_network else None,
            profile_url=link.profile_url,
        )
        for link in parliamentarian.social_networks
        if link.profile_url or (link.social_network and link.social_network.name)
    ]
    return ParliamentarianDetailOut(**base.model_dump(), social_networks=social_networks)


def _apply_situacao_filter(stmt, situacao: str):
    """Aplica filtro de situação parlamentar com base na coluna status."""
    is_deputado = Parliamentarian.type.ilike("%Deput%")
    is_senador = Parliamentarian.type.ilike("%Senad%")

    if situacao == "exercicio":
        return stmt.where(
            or_(
                and_(is_deputado, Parliamentarian.status.ilike("%exerc%")),
                is_senador,
            )
        )
    if situacao == "afastado":
        return stmt.where(
            or_(
                Parliamentarian.status.ilike("%afast%"),
                Parliamentarian.status.ilike("%fora de exerc%"),
            )
        )
    if situacao == "licenciado":
        return stmt.where(Parliamentarian.status.ilike("%licenc%"))
    if situacao == "fim_de_mandato":
        return stmt.where(
            or_(
                Parliamentarian.status.ilike("%fim de mandato%"),
                and_(
                    is_deputado,
                    or_(
                        Parliamentarian.status.is_(None),
                        Parliamentarian.name.is_(None),
                        Parliamentarian.party.is_(None),
                    ),
                ),
            )
        )
    return stmt


@router.get("/", response_model=List[ParliamentarianOut])
def list_parliamentarians(
    *,
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    party: Optional[str] = Query(default=None, description="Filtrar por partido"),
    type: Optional[List[Literal["deputado", "senado"]]] = Query(
        default=None,
        description="Filtrar por tipo de parlamentar: deputado, senado (pode repetir para ambos).",
    ),
    situacao: Optional[Literal["exercicio", "afastado", "licenciado", "fim_de_mandato"]] = Query(
        default=None,
        description="Filtrar por situação do mandato: exercicio, afastado, licenciado, fim_de_mandato.",
    ),
    created_from: Optional[datetime] = Query(
        default=None,
        description="Filtra por registros criados a partir deste instante (inclusive).",
    ),
    created_to: Optional[datetime] = Query(
        default=None,
        description="Filtra por registros criados até este instante (inclusive).",
    ),
    updated_from: Optional[datetime] = Query(
        default=None,
        description="Filtra por registros atualizados a partir deste instante (inclusive).",
    ),
    updated_to: Optional[datetime] = Query(
        default=None,
        description="Filtra por registros atualizados até este instante (inclusive).",
    ),
    sort_by: Literal["created_at", "updated_at", "name", "full_name", "party"] = Query(
        default="created_at",
        description="Campo usado para ordenação.",
    ),
    sort_order: Literal["asc", "desc"] = Query(
        default="desc",
        description="Direção da ordenação.",
    ),
) -> List[Parliamentarian]:
    """Retorna uma lista paginada de parlamentares."""
    stmt = select(Parliamentarian).offset(offset).limit(limit)

    if party:
        stmt = stmt.where(Parliamentarian.party.ilike(f"%{party}%"))

    if type:
        normalized_types = set(type)
        type_filters = []
        if "deputado" in normalized_types:
            type_filters.append(Parliamentarian.type.ilike("%Deput%"))
        if "senado" in normalized_types:
            # Banco pode armazenar "senador" ou "senado".
            type_filters.append(Parliamentarian.type.ilike("%Senad%"))
        if type_filters:
            stmt = stmt.where(or_(*type_filters))

    if situacao is not None:
        stmt = _apply_situacao_filter(stmt, situacao)

    if created_from is not None:
        stmt = stmt.where(Parliamentarian.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(Parliamentarian.created_at <= created_to)
    if updated_from is not None:
        stmt = stmt.where(Parliamentarian.updated_at >= updated_from)
    if updated_to is not None:
        stmt = stmt.where(Parliamentarian.updated_at <= updated_to)

    sortable_columns = {
        "created_at": Parliamentarian.created_at,
        "updated_at": Parliamentarian.updated_at,
        "name": Parliamentarian.name,
        "full_name": Parliamentarian.full_name,
        "party": Parliamentarian.party,
    }
    sort_column = sortable_columns[sort_by]
    stmt = stmt.order_by(asc(sort_column) if sort_order == "asc" else desc(sort_column))

    result = db.execute(stmt)
    return result.scalars().all()


@router.get("/{parliamentarian_id}", response_model=ParliamentarianDetailOut)
def get_parliamentarian(
    parliamentarian_id: int,
    db: Session = Depends(get_db),
) -> ParliamentarianDetailOut:
    """Busca um parlamentar específico pelo identificador."""
    stmt = (
        select(Parliamentarian)
        .where(Parliamentarian.id == parliamentarian_id)
        .options(
            selectinload(Parliamentarian.social_networks).selectinload(
                ParliamentarianSocialNetwork.social_network
            )
        )
    )
    result = db.execute(stmt).scalar_one_or_none()

    if result is None:
        raise HTTPException(status_code=404, detail="Parlamentar não encontrado.")

    return _serialize_parliamentarian_detail(result)


__all__ = ["router"]

