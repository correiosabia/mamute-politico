"""Rotas para votações nominais (roll call votes)."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import asc, desc, inspect as sqlalchemy_inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

try:
    # Execução como pacote (api.routers.roll_call_votes).
    from ..db.models.parliamentarian import Parliamentarian
    from ..db.models.proposition import Proposition
    from ..db.models.roll_call_votes import RollCallVote
    from ..dependencies import get_db
except (ImportError, ValueError):
    # Execução local dentro de api/ sem reconhecimento de pacote.
    from db.models.parliamentarian import Parliamentarian
    from db.models.proposition import Proposition
    from db.models.roll_call_votes import RollCallVote
    from dependencies import get_db

router = APIRouter(prefix="/roll-call-votes", tags=["roll_call_votes"])


class RollCallVoteOut(BaseModel):
    """Representação serializada de uma votação nominal."""

    id: int
    parliamentarian_id: int
    proposition_id: int
    proposition_title: Optional[str] = None
    vote: Optional[str] = None
    description: Optional[str] = None
    link: Optional[str] = None
    proposition_votes_link: Optional[str] = None
    date_vote: Optional[date] = None
    created_at: datetime
    updated_at: datetime
    parliamentarian_name: Optional[str] = None
    parliamentarian_party: Optional[str] = None
    parliamentarian_state_elected: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


def _extract_date_vote_legacy(proposition: Optional[Proposition]) -> Optional[date]:
    """Fallback enquanto o backfill_vote_dates ainda não populou os históricos.

    Extrai a data de votação do JSON `proposition.details.decisao_destino.Decisao.Data`,
    que só existe para uma fração dos votos do Senado (~3% segundo auditoria) e
    nunca para a Câmara. Será removido em PR posterior, quando `vote_date` tiver
    100% de cobertura.
    """
    if proposition is None or not isinstance(proposition.details, dict):
        return None

    decision = (
        proposition.details.get("decisao_destino", {})
        .get("Decisao", {})
    )
    raw_date = decision.get("Data")
    if not isinstance(raw_date, str) or not raw_date:
        return None

    try:
        return date.fromisoformat(raw_date)
    except ValueError:
        return None


def _resolve_date_vote(vote: RollCallVote) -> Optional[date]:
    """Prefere `vote.vote_date` (coluna populada pelo crawler); cai no extrator
    legado apenas se a coluna estiver vazia (votos pré-PR aguardando backfill)."""
    if vote.vote_date is not None:
        return vote.vote_date
    return _extract_date_vote_legacy(vote.proposition)


def _serialize_roll_call_vote(vote: RollCallVote) -> RollCallVoteOut:
    proposition_votes_link: Optional[str] = None
    if vote.proposition and isinstance(vote.proposition.link, str) and vote.proposition.link:
        proposition_votes_link = f"{vote.proposition.link.rstrip('/')}/votacoes"

    mp_name: Optional[str] = None
    mp_party: Optional[str] = None
    mp_uf: Optional[str] = None
    if vote.parliamentarian is not None:
        p = vote.parliamentarian
        raw_name = (p.full_name or p.name or "").strip()
        mp_name = raw_name or None
        if p.party and str(p.party).strip():
            mp_party = str(p.party).strip()
        if p.state_elected and str(p.state_elected).strip():
            mp_uf = str(p.state_elected).strip()

    return RollCallVoteOut(
        id=vote.id,
        parliamentarian_id=vote.parliamentarian_id,
        proposition_id=vote.proposition_id,
        proposition_title=vote.proposition.title if vote.proposition else None,
        vote=vote.vote,
        description=vote.description,
        link=vote.link,
        proposition_votes_link=proposition_votes_link,
        date_vote=_resolve_date_vote(vote),
        created_at=vote.created_at,
        updated_at=vote.updated_at,
        parliamentarian_name=mp_name,
        parliamentarian_party=mp_party,
        parliamentarian_state_elected=mp_uf,
    )


def _clean_optional_text(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _table_has_column(db: Session, table_name: str, column_name: str) -> bool:
    try:
        columns = sqlalchemy_inspect(db.get_bind()).get_columns(table_name)
    except SQLAlchemyError:
        return True
    return any(column.get("name") == column_name for column in columns)


def _serialize_roll_call_vote_without_vote_date(row) -> RollCallVoteOut:
    proposition_link = _clean_optional_text(row["proposition_link"])
    proposition_votes_link = (
        f"{proposition_link.rstrip('/')}/votacoes" if proposition_link else None
    )
    parliamentarian_name = _clean_optional_text(
        row["parliamentarian_full_name"]
    ) or _clean_optional_text(row["parliamentarian_name"])

    return RollCallVoteOut(
        id=int(row["id"]),
        parliamentarian_id=int(row["parliamentarian_id"]),
        proposition_id=int(row["proposition_id"]),
        proposition_title=_clean_optional_text(row["proposition_title"]),
        vote=_clean_optional_text(row["vote"]),
        description=_clean_optional_text(row["description"]),
        link=_clean_optional_text(row["link"]),
        proposition_votes_link=proposition_votes_link,
        date_vote=None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        parliamentarian_name=parliamentarian_name,
        parliamentarian_party=_clean_optional_text(row["parliamentarian_party"]),
        parliamentarian_state_elected=_clean_optional_text(
            row["parliamentarian_state_elected"]
        ),
    )


def _roll_call_votes_without_vote_date_stmt():
    return (
        select(
            RollCallVote.id.label("id"),
            RollCallVote.parliamentarian_id.label("parliamentarian_id"),
            RollCallVote.proposition_id.label("proposition_id"),
            RollCallVote.vote.label("vote"),
            RollCallVote.description.label("description"),
            RollCallVote.link.label("link"),
            RollCallVote.created_at.label("created_at"),
            RollCallVote.updated_at.label("updated_at"),
            Proposition.title.label("proposition_title"),
            Proposition.link.label("proposition_link"),
            Parliamentarian.name.label("parliamentarian_name"),
            Parliamentarian.full_name.label("parliamentarian_full_name"),
            Parliamentarian.party.label("parliamentarian_party"),
            Parliamentarian.state_elected.label("parliamentarian_state_elected"),
        )
        .outerjoin(Proposition, Proposition.id == RollCallVote.proposition_id)
        .outerjoin(
            Parliamentarian,
            Parliamentarian.id == RollCallVote.parliamentarian_id,
        )
    )


def _list_roll_call_votes_without_vote_date(
    db: Session,
    *,
    limit: int,
    offset: int = 0,
    proposition_id: Optional[int] = None,
    parliamentarian_id: Optional[int] = None,
    parliamentarian_ids: Optional[List[int]] = None,
    created_from: Optional[datetime] = None,
    created_to: Optional[datetime] = None,
    updated_from: Optional[datetime] = None,
    updated_to: Optional[datetime] = None,
    sort_by: Literal[
        "created_at",
        "updated_at",
        "id",
        "parliamentarian_id",
        "proposition_id",
    ] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
) -> List[RollCallVoteOut]:
    stmt = _roll_call_votes_without_vote_date_stmt()
    if proposition_id is not None:
        stmt = stmt.where(RollCallVote.proposition_id == proposition_id)
    if parliamentarian_id is not None:
        stmt = stmt.where(RollCallVote.parliamentarian_id == parliamentarian_id)
    if parliamentarian_ids is not None:
        stmt = stmt.where(RollCallVote.parliamentarian_id.in_(parliamentarian_ids))
    if created_from is not None:
        stmt = stmt.where(RollCallVote.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(RollCallVote.created_at <= created_to)
    if updated_from is not None:
        stmt = stmt.where(RollCallVote.updated_at >= updated_from)
    if updated_to is not None:
        stmt = stmt.where(RollCallVote.updated_at <= updated_to)

    sortable_columns = {
        "created_at": RollCallVote.created_at,
        "updated_at": RollCallVote.updated_at,
        "id": RollCallVote.id,
        "parliamentarian_id": RollCallVote.parliamentarian_id,
        "proposition_id": RollCallVote.proposition_id,
    }
    sort_column = sortable_columns[sort_by]
    stmt = stmt.order_by(asc(sort_column) if sort_order == "asc" else desc(sort_column))
    stmt = stmt.offset(offset).limit(limit)

    return [
        _serialize_roll_call_vote_without_vote_date(row)
        for row in db.execute(stmt).mappings().all()
    ]


@router.get("/", response_model=List[RollCallVoteOut])
@router.get("/votacoes", response_model=List[RollCallVoteOut])
def list_roll_call_votes(
    *,
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    proposition_id: Optional[int] = Query(
        None, description="Filtra pela proposição relacionada."
    ),
    parliamentarian_id: Optional[int] = Query(
        None, description="Filtra pelo parlamentar que votou."
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
        "id",
        "parliamentarian_id",
        "proposition_id",
    ] = Query(default="created_at", description="Campo usado para ordenação."),
    sort_order: Literal["asc", "desc"] = Query(
        default="desc",
        description="Direção da ordenação.",
    ),
) -> List[RollCallVoteOut]:
    """Retorna uma lista paginada de votações nominais."""
    if not _table_has_column(db, "roll_call_votes", "vote_date"):
        return _list_roll_call_votes_without_vote_date(
            db,
            limit=limit,
            offset=offset,
            proposition_id=proposition_id,
            parliamentarian_id=parliamentarian_id,
            created_from=created_from,
            created_to=created_to,
            updated_from=updated_from,
            updated_to=updated_to,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    stmt = (
        select(RollCallVote)
        .options(
            selectinload(RollCallVote.proposition),
            selectinload(RollCallVote.parliamentarian),
        )
        .offset(offset)
        .limit(limit)
    )
    if proposition_id is not None:
        stmt = stmt.where(RollCallVote.proposition_id == proposition_id)
    if parliamentarian_id is not None:
        stmt = stmt.where(RollCallVote.parliamentarian_id == parliamentarian_id)
    if created_from is not None:
        stmt = stmt.where(RollCallVote.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(RollCallVote.created_at <= created_to)
    if updated_from is not None:
        stmt = stmt.where(RollCallVote.updated_at >= updated_from)
    if updated_to is not None:
        stmt = stmt.where(RollCallVote.updated_at <= updated_to)

    sortable_columns = {
        "created_at": RollCallVote.created_at,
        "updated_at": RollCallVote.updated_at,
        "id": RollCallVote.id,
        "parliamentarian_id": RollCallVote.parliamentarian_id,
        "proposition_id": RollCallVote.proposition_id,
    }
    sort_column = sortable_columns[sort_by]
    stmt = stmt.order_by(asc(sort_column) if sort_order == "asc" else desc(sort_column))

    result = db.execute(stmt)
    votes = result.scalars().all()
    return [_serialize_roll_call_vote(vote) for vote in votes]


@router.get("/{vote_id}", response_model=RollCallVoteOut)
@router.get("/votacoes/{vote_id}", response_model=RollCallVoteOut)
def get_roll_call_vote(
    vote_id: int,
    db: Session = Depends(get_db),
) -> RollCallVoteOut:
    """Busca uma votação nominal pelo identificador."""
    if not _table_has_column(db, "roll_call_votes", "vote_date"):
        stmt_without_vote_date = _roll_call_votes_without_vote_date_stmt().where(
            RollCallVote.id == vote_id
        )
        row = db.execute(stmt_without_vote_date).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="Votação não encontrada.")
        return _serialize_roll_call_vote_without_vote_date(row)

    stmt = (
        select(RollCallVote)
        .options(
            selectinload(RollCallVote.proposition),
            selectinload(RollCallVote.parliamentarian),
        )
        .where(RollCallVote.id == vote_id)
    )
    result = db.execute(stmt).scalar_one_or_none()

    if result is None:
        raise HTTPException(status_code=404, detail="Votação não encontrada.")

    return _serialize_roll_call_vote(result)


__all__ = ["router"]
