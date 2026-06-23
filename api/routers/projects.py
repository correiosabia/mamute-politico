"""Rotas relacionadas a projetos e seus favoritos."""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from typing import List, Literal, Optional
from zoneinfo import ZoneInfo
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session, selectinload

try:
    # Execução como pacote (api.routers.projects).
    from ..db.models.parliamentarian import Parliamentarian
    from ..db.models.authors_proposition import AuthorsProposition
    from ..db.models.committee_attendance import CommitteeAttendance
    from ..db.models.plenary_attendance import PlenaryAttendance
    from ..db.models.proposition import Proposition
    from ..db.models.project import Projetos, ProjetosParliamentarian
    from ..db.models.roll_call_votes import RollCallVote
    from ..db.models.speeches_transcripts import SpeechesTranscript
    from ..dependencies import get_db
    from .propositions import PropositionOut, _serialize_proposition
    from .roll_call_votes import (
        RollCallVoteOut,
        _list_roll_call_votes_without_vote_date,
        _serialize_roll_call_vote,
        _table_has_column,
    )
except (ImportError, ValueError):  # pragma: no cover - caminho alternativo
    # Execução local dentro de api/ sem reconhecimento de pacote.
    from db.models.parliamentarian import Parliamentarian
    from db.models.authors_proposition import AuthorsProposition
    from db.models.committee_attendance import CommitteeAttendance
    from db.models.plenary_attendance import PlenaryAttendance
    from db.models.proposition import Proposition
    from db.models.project import Projetos, ProjetosParliamentarian
    from db.models.roll_call_votes import RollCallVote
    from db.models.speeches_transcripts import SpeechesTranscript
    from dependencies import get_db
    from routers.propositions import PropositionOut, _serialize_proposition
    from routers.roll_call_votes import (
        RollCallVoteOut,
        _list_roll_call_votes_without_vote_date,
        _serialize_roll_call_vote,
        _table_has_column,
    )


router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectFavoriteOut(BaseModel):
    """Representação serializada do vínculo de favorito entre projeto e parlamentar."""

    id: int
    projeto_id: int
    parliamentarian_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectFavoriteCreate(BaseModel):
    """Dados necessários para criar um novo favorito de projeto."""

    parliamentarian_id: int


class ProjectFavoriteQuotaOut(BaseModel):
    """Limite de parlamentares monitorados para o projeto autenticado."""

    limit: int
    used: int
    remaining: int
    limit_reached: bool


class ProjectDashboardStatsOut(BaseModel):
    """Estatísticas dos últimos 3 meses do dashboard do projeto autenticado."""

    propositions_this_week: int
    attendance_avg_percent: Optional[int] = None
    recent_votes_count: int
    speeches_count: int


class ProjectDashboardActivityAuthorOut(BaseModel):
    """Parlamentar monitorado associado a uma atividade do dashboard."""

    id: int
    name: Optional[str] = None
    full_name: Optional[str] = None
    party: Optional[str] = None
    state_elected: Optional[str] = None
    type: Optional[str] = None


class ProjectDashboardActivityPropositionOut(PropositionOut):
    """Proposição com autores monitorados pelo projeto autenticado."""

    monitored_authors: List[ProjectDashboardActivityAuthorOut]


class ProjectDashboardActivityOut(BaseModel):
    """Atividades recentes dos parlamentares monitorados pelo projeto autenticado."""

    propositions: List[ProjectDashboardActivityPropositionOut]
    votes: List[RollCallVoteOut]


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return normalized.lower().strip()


def _is_present_status(value: Optional[str]) -> bool:
    normalized = _normalize_text(value)
    if "presen" not in normalized:
        return False
    if "nao" in normalized or "não" in normalized:
        return False
    return True


def _subtract_months(value: date, months: int) -> date:
    target_year = value.year
    target_month = value.month - months
    while target_month <= 0:
        target_month += 12
        target_year -= 1
    target_day = min(value.day, calendar.monthrange(target_year, target_month)[1])
    return date(target_year, target_month, target_day)


def _last_three_months_range_sao_paulo() -> tuple[date, date, datetime, datetime]:
    tz = ZoneInfo("America/Sao_Paulo")
    now_local = datetime.now(tz)
    range_start_date = _subtract_months(now_local.date(), 3)
    range_end_date = now_local.date()
    range_start_dt = datetime.combine(range_start_date, time.min, tzinfo=tz)
    range_end_dt_exclusive = datetime.combine(
        range_end_date + timedelta(days=1),
        time.min,
        tzinfo=tz,
    )
    return range_start_date, range_end_date, range_start_dt, range_end_dt_exclusive


def _get_project_favorite_ids(db: Session, project_id: int) -> List[int]:
    stmt = select(ProjetosParliamentarian.parliamentarian_id).where(
        ProjetosParliamentarian.projeto_id == project_id
    )
    return [int(item) for item in db.execute(stmt).scalars().all()]


def _count_propositions_in_range(
    db: Session, parliamentarian_ids: List[int], range_start: date, range_end: date
) -> int:
    stmt = (
        select(func.count(func.distinct(Proposition.id)))
        .select_from(AuthorsProposition)
        .join(Proposition, Proposition.id == AuthorsProposition.proposition_id)
        .where(AuthorsProposition.parliamentarian_id.in_(parliamentarian_ids))
        .where(Proposition.presentation_date.is_not(None))
        .where(Proposition.presentation_date >= range_start)
        .where(Proposition.presentation_date <= range_end)
    )
    return int(db.execute(stmt).scalar_one() or 0)


def _count_recent_votes(
    db: Session,
    parliamentarian_ids: List[int],
    range_start_dt: datetime,
    range_end_dt_exclusive: datetime,
) -> int:
    stmt = select(func.count(RollCallVote.id)).where(
        RollCallVote.parliamentarian_id.in_(parliamentarian_ids),
        RollCallVote.created_at >= range_start_dt,
        RollCallVote.created_at < range_end_dt_exclusive,
    )
    return int(db.execute(stmt).scalar_one() or 0)


def _count_speeches_in_range(
    db: Session, parliamentarian_ids: List[int], range_start: date, range_end: date
) -> int:
    stmt = select(func.count(SpeechesTranscript.id)).where(
        SpeechesTranscript.parliamentarian_id.in_(parliamentarian_ids),
        SpeechesTranscript.date.is_not(None),
        SpeechesTranscript.date >= range_start,
        SpeechesTranscript.date <= range_end,
    )
    return int(db.execute(stmt).scalar_one() or 0)


def _calculate_attendance_avg_percent(
    db: Session, parliamentarian_ids: List[int], range_start: date, range_end: date
) -> Optional[int]:
    plenary_stmt = select(
        PlenaryAttendance.session_attendance,
        PlenaryAttendance.daily_attendance_justification,
    ).where(
        PlenaryAttendance.parliamentarian_id.in_(parliamentarian_ids),
        PlenaryAttendance.date.is_not(None),
        PlenaryAttendance.date >= range_start,
        PlenaryAttendance.date <= range_end,
    )
    committee_stmt = select(CommitteeAttendance.frequency).where(
        CommitteeAttendance.parliamentarian_id.in_(parliamentarian_ids),
        CommitteeAttendance.date.is_not(None),
        CommitteeAttendance.date >= range_start,
        CommitteeAttendance.date <= range_end,
    )

    presence_scores: List[int] = []
    for session_attendance, daily_justification in db.execute(plenary_stmt).all():
        status_value = session_attendance or daily_justification
        presence_scores.append(1 if _is_present_status(status_value) else 0)

    for (frequency,) in db.execute(committee_stmt).all():
        presence_scores.append(1 if _is_present_status(frequency) else 0)

    if not presence_scores:
        return None
    avg_ratio = sum(presence_scores) / len(presence_scores)
    return int(round(avg_ratio * 100))


def _list_project_dashboard_propositions(
    db: Session,
    parliamentarian_ids: List[int],
    limit: int,
) -> List[ProjectDashboardActivityPropositionOut]:
    authorship_proposition_ids = select(AuthorsProposition.proposition_id).where(
        AuthorsProposition.parliamentarian_id.in_(parliamentarian_ids)
    )
    stmt = (
        select(Proposition)
        .where(Proposition.id.in_(authorship_proposition_ids))
        .order_by(
            desc(Proposition.presentation_date).nulls_last(),
            desc(Proposition.created_at),
            desc(Proposition.id),
        )
        .limit(limit)
    )
    propositions = db.execute(stmt).scalars().all()
    if not propositions:
        return []

    proposition_ids = [int(proposition.id) for proposition in propositions]
    favorite_author_links = (
        select(
            AuthorsProposition.proposition_id,
            AuthorsProposition.parliamentarian_id,
        )
        .where(AuthorsProposition.proposition_id.in_(proposition_ids))
        .where(AuthorsProposition.parliamentarian_id.in_(parliamentarian_ids))
        .distinct()
        .subquery()
    )
    authors_stmt = (
        select(favorite_author_links.c.proposition_id, Parliamentarian)
        .join(
            Parliamentarian,
            Parliamentarian.id == favorite_author_links.c.parliamentarian_id,
        )
        .order_by(
            favorite_author_links.c.proposition_id,
            asc(Parliamentarian.name),
            asc(Parliamentarian.id),
        )
    )
    monitored_authors_by_proposition: dict[int, List[ProjectDashboardActivityAuthorOut]] = {}
    for proposition_id, parliamentarian in db.execute(authors_stmt).all():
        monitored_authors_by_proposition.setdefault(int(proposition_id), []).append(
            ProjectDashboardActivityAuthorOut(
                id=int(parliamentarian.id),
                name=parliamentarian.name,
                full_name=parliamentarian.full_name,
                party=parliamentarian.party,
                state_elected=parliamentarian.state_elected,
                type=parliamentarian.type,
            )
        )

    return [
        ProjectDashboardActivityPropositionOut(
            **_serialize_proposition(proposition).model_dump(),
            monitored_authors=monitored_authors_by_proposition.get(
                int(proposition.id),
                [],
            ),
        )
        for proposition in propositions
    ]


def _list_project_dashboard_votes(
    db: Session,
    parliamentarian_ids: List[int],
    limit: int,
) -> List[RollCallVoteOut]:
    if not _table_has_column(db, "roll_call_votes", "vote_date"):
        return _list_roll_call_votes_without_vote_date(
            db,
            parliamentarian_ids=parliamentarian_ids,
            limit=limit,
        )

    stmt = (
        select(RollCallVote)
        .options(
            selectinload(RollCallVote.proposition),
            selectinload(RollCallVote.parliamentarian),
        )
        .where(RollCallVote.parliamentarian_id.in_(parliamentarian_ids))
        .order_by(
            desc(RollCallVote.created_at),
            desc(RollCallVote.id),
        )
        .limit(limit)
    )
    votes = db.execute(stmt).scalars().all()
    return [_serialize_roll_call_vote(vote) for vote in votes]


def _ensure_active_project(
    db: Session,
    project_id: int,
    *,
    lock_for_update: bool = False,
) -> Projetos:
    stmt = select(Projetos).where(Projetos.id == project_id)
    if lock_for_update:
        stmt = stmt.with_for_update()
    project = db.execute(stmt).scalar_one_or_none()
    if project is None or getattr(project, "deleted_at", None) is not None:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    return project


def _get_project_from_token_email(request: Request, db: Session) -> Projetos:
    token_email = getattr(request.state, "token_email", None)
    if not token_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sem e-mail (sub) para identificar o projeto.",
        )

    stmt = select(Projetos).where(
        Projetos.email == token_email,
        Projetos.deleted_at.is_(None),
    )
    project = db.execute(stmt).scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projeto não encontrado para o e-mail autenticado.",
        )

    return project


def _ensure_parliamentarian_exists(db: Session, parliamentarian_id: int) -> Parliamentarian:
    parliamentarian = db.get(Parliamentarian, parliamentarian_id)
    if parliamentarian is None:
        raise HTTPException(status_code=404, detail="Parlamentar não encontrado.")
    return parliamentarian


def _get_project_favorite_count(db: Session, project_id: int) -> int:
    stmt = select(func.count(ProjetosParliamentarian.id)).where(
        ProjetosParliamentarian.projeto_id == project_id,
        ProjetosParliamentarian.deleted_at.is_(None),
    )
    return int(db.execute(stmt).scalar_one() or 0)


def _project_favorite_limit(project: Projetos) -> int:
    return max(0, int(project.qtd_termos or 0))


def _build_project_favorite_quota(db: Session, project: Projetos) -> ProjectFavoriteQuotaOut:
    limit = _project_favorite_limit(project)
    used = _get_project_favorite_count(db, int(project.id))
    remaining = max(0, limit - used)
    return ProjectFavoriteQuotaOut(
        limit=limit,
        used=used,
        remaining=remaining,
        limit_reached=used >= limit,
    )


def _ensure_project_favorite_quota_available(db: Session, project: Projetos) -> None:
    quota = _build_project_favorite_quota(db, project)
    if quota.limit_reached:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Limite de parlamentares monitorados atingido para seu plano "
                f"({quota.used}/{quota.limit})."
            ),
        )


def _create_project_favorite(
    db: Session,
    project_id: int,
    parliamentarian_id: int,
) -> ProjetosParliamentarian:
    project = _ensure_active_project(db, project_id, lock_for_update=True)
    _ensure_parliamentarian_exists(db, parliamentarian_id)

    existing_stmt = select(ProjetosParliamentarian).where(
        ProjetosParliamentarian.projeto_id == project_id,
        ProjetosParliamentarian.parliamentarian_id == parliamentarian_id,
    )
    existing = db.execute(existing_stmt).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Parlamentar já está favoritado neste projeto.",
        )

    _ensure_project_favorite_quota_available(db, project)

    favorite = ProjetosParliamentarian(
        projeto_id=project_id,
        parliamentarian_id=parliamentarian_id,
    )
    db.add(favorite)
    db.commit()
    db.refresh(favorite)
    return favorite


def _delete_project_favorite(db: Session, project_id: int, parliamentarian_id: int) -> None:
    _ensure_active_project(db, project_id)
    stmt = select(ProjetosParliamentarian).where(
        ProjetosParliamentarian.projeto_id == project_id,
        ProjetosParliamentarian.parliamentarian_id == parliamentarian_id,
    )
    favorite = db.execute(stmt).scalar_one_or_none()

    if favorite is None:
        raise HTTPException(
            status_code=404,
            detail="Favorito não encontrado para o projeto informado.",
        )

    db.delete(favorite)
    db.commit()


@router.get(
    "/me/favorites",
    response_model=List[ProjectFavoriteOut],
    summary="Lista favoritos do projeto do usuário autenticado",
)
def list_my_project_favorites(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    created_from: Optional[datetime] = Query(
        None,
        description="Filtra por favoritos criados a partir deste instante (inclusive).",
    ),
    created_to: Optional[datetime] = Query(
        None,
        description="Filtra por favoritos criados até este instante (inclusive).",
    ),
    updated_from: Optional[datetime] = Query(
        None,
        description="Filtra por favoritos atualizados a partir deste instante (inclusive).",
    ),
    updated_to: Optional[datetime] = Query(
        None,
        description="Filtra por favoritos atualizados até este instante (inclusive).",
    ),
    sort_by: Literal["created_at", "updated_at", "id", "parliamentarian_id"] = Query(
        default="created_at",
        description="Campo usado para ordenação.",
    ),
    sort_order: Literal["asc", "desc"] = Query(
        default="desc",
        description="Direção da ordenação.",
    ),
) -> List[ProjetosParliamentarian]:
    """Retorna os favoritos do projeto identificado pelo e-mail do token JWT."""
    project = _get_project_from_token_email(request, db)
    stmt = select(ProjetosParliamentarian).where(ProjetosParliamentarian.projeto_id == project.id)
    if created_from is not None:
        stmt = stmt.where(ProjetosParliamentarian.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(ProjetosParliamentarian.created_at <= created_to)
    if updated_from is not None:
        stmt = stmt.where(ProjetosParliamentarian.updated_at >= updated_from)
    if updated_to is not None:
        stmt = stmt.where(ProjetosParliamentarian.updated_at <= updated_to)
    sortable_columns = {
        "created_at": ProjetosParliamentarian.created_at,
        "updated_at": ProjetosParliamentarian.updated_at,
        "id": ProjetosParliamentarian.id,
        "parliamentarian_id": ProjetosParliamentarian.parliamentarian_id,
    }
    sort_column = sortable_columns[sort_by]
    stmt = stmt.order_by(asc(sort_column) if sort_order == "asc" else desc(sort_column))
    stmt = stmt.offset(offset).limit(limit)
    favorites = db.execute(stmt)
    return favorites.scalars().all()


@router.get(
    "/me/favorites/quota",
    response_model=ProjectFavoriteQuotaOut,
    summary="Retorna limite de favoritos do projeto autenticado",
)
def get_my_project_favorites_quota(
    request: Request,
    db: Session = Depends(get_db),
) -> ProjectFavoriteQuotaOut:
    """Retorna limite, uso e saldo de parlamentares monitorados do projeto."""
    project = _get_project_from_token_email(request, db)
    return _build_project_favorite_quota(db, project)


@router.post(
    "/me/favorites",
    response_model=ProjectFavoriteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Adiciona favorito ao projeto do usuário autenticado",
)
def add_my_project_favorite(
    request: Request,
    payload: ProjectFavoriteCreate,
    db: Session = Depends(get_db),
) -> ProjetosParliamentarian:
    """Cria favorito usando o projeto identificado pelo e-mail do token JWT."""
    project = _get_project_from_token_email(request, db)
    return _create_project_favorite(db, project.id, payload.parliamentarian_id)


@router.delete(
    "/me/favorites/{parliamentarian_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove favorito do projeto do usuário autenticado",
)
def remove_my_project_favorite(
    request: Request,
    parliamentarian_id: int,
    db: Session = Depends(get_db),
) -> Response:
    """Remove favorito usando o projeto identificado pelo e-mail do token JWT."""
    project = _get_project_from_token_email(request, db)
    _delete_project_favorite(db, project.id, parliamentarian_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me/dashboard-activity",
    response_model=ProjectDashboardActivityOut,
    summary="Atividades recentes dos parlamentares favoritados no projeto autenticado",
)
def get_my_dashboard_activity(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
) -> ProjectDashboardActivityOut:
    """Retorna atividades recentes escopadas aos parlamentares favoritados."""
    project = _get_project_from_token_email(request, db)
    parliamentarian_ids = _get_project_favorite_ids(db, project.id)
    if not parliamentarian_ids:
        return ProjectDashboardActivityOut(propositions=[], votes=[])

    return ProjectDashboardActivityOut(
        propositions=_list_project_dashboard_propositions(
            db,
            parliamentarian_ids,
            limit,
        ),
        votes=_list_project_dashboard_votes(
            db,
            parliamentarian_ids,
            limit,
        ),
    )


@router.get(
    "/{project_id}/favorites",
    response_model=List[ProjectFavoriteOut],
    summary="Lista favoritos de um projeto",
)
def list_project_favorites(
    project_id: int,
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    created_from: Optional[datetime] = Query(
        None,
        description="Filtra por favoritos criados a partir deste instante (inclusive).",
    ),
    created_to: Optional[datetime] = Query(
        None,
        description="Filtra por favoritos criados até este instante (inclusive).",
    ),
    updated_from: Optional[datetime] = Query(
        None,
        description="Filtra por favoritos atualizados a partir deste instante (inclusive).",
    ),
    updated_to: Optional[datetime] = Query(
        None,
        description="Filtra por favoritos atualizados até este instante (inclusive).",
    ),
    sort_by: Literal["created_at", "updated_at", "id", "parliamentarian_id"] = Query(
        default="created_at",
        description="Campo usado para ordenação.",
    ),
    sort_order: Literal["asc", "desc"] = Query(
        default="desc",
        description="Direção da ordenação.",
    ),
) -> List[ProjetosParliamentarian]:
    """Retorna os parlamentares marcados como favoritos por um projeto específico."""
    _ensure_active_project(db, project_id)

    stmt = select(ProjetosParliamentarian).where(ProjetosParliamentarian.projeto_id == project_id)
    if created_from is not None:
        stmt = stmt.where(ProjetosParliamentarian.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(ProjetosParliamentarian.created_at <= created_to)
    if updated_from is not None:
        stmt = stmt.where(ProjetosParliamentarian.updated_at >= updated_from)
    if updated_to is not None:
        stmt = stmt.where(ProjetosParliamentarian.updated_at <= updated_to)
    sortable_columns = {
        "created_at": ProjetosParliamentarian.created_at,
        "updated_at": ProjetosParliamentarian.updated_at,
        "id": ProjetosParliamentarian.id,
        "parliamentarian_id": ProjetosParliamentarian.parliamentarian_id,
    }
    sort_column = sortable_columns[sort_by]
    stmt = stmt.order_by(asc(sort_column) if sort_order == "asc" else desc(sort_column))
    stmt = stmt.offset(offset).limit(limit)
    favorites = db.execute(stmt)
    return favorites.scalars().all()


@router.post(
    "/{project_id}/favorites",
    response_model=ProjectFavoriteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Adiciona um parlamentar aos favoritos do projeto",
)
def add_project_favorite(
    project_id: int,
    payload: ProjectFavoriteCreate,
    db: Session = Depends(get_db),
) -> ProjetosParliamentarian:
    """Cria o vínculo de favorito entre um projeto e um parlamentar."""
    return _create_project_favorite(db, project_id, payload.parliamentarian_id)


@router.delete(
    "/{project_id}/favorites/{parliamentarian_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove um parlamentar dos favoritos do projeto",
)
def remove_project_favorite(
    project_id: int,
    parliamentarian_id: int,
    db: Session = Depends(get_db),
) -> Response:
    """Remove o vínculo de favorito entre um projeto e um parlamentar."""
    _delete_project_favorite(db, project_id, parliamentarian_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me/dashboard-stats",
    response_model=ProjectDashboardStatsOut,
    summary="Estatísticas dos últimos 3 meses do dashboard do projeto autenticado",
)
def get_my_dashboard_stats(
    request: Request,
    db: Session = Depends(get_db),
) -> ProjectDashboardStatsOut:
    """Retorna estatísticas dos últimos 3 meses para parlamentares favoritados no projeto."""
    project = _get_project_from_token_email(request, db)
    parliamentarian_ids = _get_project_favorite_ids(db, project.id)
    if not parliamentarian_ids:
        return ProjectDashboardStatsOut(
            propositions_this_week=0,
            attendance_avg_percent=None,
            recent_votes_count=0,
            speeches_count=0,
        )

    range_start, range_end, range_start_dt, range_end_dt_exclusive = (
        _last_three_months_range_sao_paulo()
    )
    return ProjectDashboardStatsOut(
        propositions_this_week=_count_propositions_in_range(
            db,
            parliamentarian_ids,
            range_start,
            range_end,
        ),
        attendance_avg_percent=_calculate_attendance_avg_percent(
            db,
            parliamentarian_ids,
            range_start,
            range_end,
        ),
        recent_votes_count=_count_recent_votes(
            db,
            parliamentarian_ids,
            range_start_dt,
            range_end_dt_exclusive,
        ),
        speeches_count=_count_speeches_in_range(
            db,
            parliamentarian_ids,
            range_start,
            range_end,
        ),
    )


@router.get(
    "/me/parliamentarians/{parliamentarian_id}/dashboard-stats",
    response_model=ProjectDashboardStatsOut,
    summary="Estatísticas dos últimos 3 meses para um parlamentar específico",
)
def get_my_parliamentarian_dashboard_stats(
    parliamentarian_id: int,
    db: Session = Depends(get_db),
) -> ProjectDashboardStatsOut:
    """Retorna estatísticas dos últimos 3 meses para um parlamentar específico."""
    _ensure_parliamentarian_exists(db, parliamentarian_id)

    range_start, range_end, range_start_dt, range_end_dt_exclusive = (
        _last_three_months_range_sao_paulo()
    )
    parliamentarian_ids = [parliamentarian_id]

    return ProjectDashboardStatsOut(
        propositions_this_week=_count_propositions_in_range(
            db,
            parliamentarian_ids,
            range_start,
            range_end,
        ),
        attendance_avg_percent=_calculate_attendance_avg_percent(
            db,
            parliamentarian_ids,
            range_start,
            range_end,
        ),
        recent_votes_count=_count_recent_votes(
            db,
            parliamentarian_ids,
            range_start_dt,
            range_end_dt_exclusive,
        ),
        speeches_count=_count_speeches_in_range(
            db,
            parliamentarian_ids,
            range_start,
            range_end,
        ),
    )


__all__ = ["router"]
