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


def _extract_photo_url_from_details(details: Optional[Dict[str, Any]]) -> Optional[str]:
    """Extrai URL da foto a partir de details (Senado ou Câmara)."""
    if not details or not isinstance(details, dict):
        return None

    direct = details.get("UrlFotoParlamentar")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    lista = details.get("lista")
    if isinstance(lista, dict):
        ident = lista.get("IdentificacaoParlamentar")
        if isinstance(ident, dict):
            url = ident.get("UrlFotoParlamentar")
            if isinstance(url, str) and url.strip():
                return url.strip()

    detalhe = details.get("detalhe")
    if isinstance(detalhe, dict):
        ident = detalhe.get("IdentificacaoParlamentar")
        if isinstance(ident, dict):
            url = ident.get("UrlFotoParlamentar")
            if isinstance(url, str) and url.strip():
                return url.strip()

    ultimo_status = details.get("ultimoStatus")
    if isinstance(ultimo_status, dict):
        url = ultimo_status.get("urlFoto")
        if isinstance(url, str) and url.strip():
            return url.strip()

    return None


def _enrich_details_with_photo_url(details: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Garante UrlFotoParlamentar em details para consumo uniforme (ex.: deputados da Câmara)."""
    if not details or not isinstance(details, dict):
        return details

    photo_url = _extract_photo_url_from_details(details)
    if not photo_url:
        return details

    if details.get("UrlFotoParlamentar"):
        return details

    enriched = dict(details)
    enriched["UrlFotoParlamentar"] = photo_url
    return enriched


def _serialize_parliamentarian(parliamentarian: Parliamentarian) -> "ParliamentarianOut":
    details = _enrich_details_with_photo_url(parliamentarian.details)
    photo_url = _extract_photo_url_from_details(details)
    return ParliamentarianOut(
        id=parliamentarian.id,
        type=parliamentarian.type,
        parliamentarian_code=parliamentarian.parliamentarian_code,
        name=parliamentarian.name,
        full_name=parliamentarian.full_name,
        email=parliamentarian.email,
        telephone=parliamentarian.telephone,
        cpf=parliamentarian.cpf,
        status=parliamentarian.status,
        party=parliamentarian.party,
        state_of_birth=parliamentarian.state_of_birth,
        city_of_birth=parliamentarian.city_of_birth,
        state_elected=parliamentarian.state_elected,
        site=parliamentarian.site,
        education=parliamentarian.education,
        office_name=parliamentarian.office_name,
        office_building=parliamentarian.office_building,
        office_number=parliamentarian.office_number,
        office_floor=parliamentarian.office_floor,
        office_email=parliamentarian.office_email,
        biography_link=parliamentarian.biography_link,
        biography_text=parliamentarian.biography_text,
        details=details,
        photo_url=photo_url,
        created_at=parliamentarian.created_at,
        updated_at=parliamentarian.updated_at,
    )


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
    photo_url: Optional[str] = None
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
) -> List[ParliamentarianOut]:
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
    return [_serialize_parliamentarian(p) for p in result.scalars().all()]


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

