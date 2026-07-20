"""Rotas administrativas — gated por require_ghost_admin (404 para não-admin)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    from ..security import require_ghost_admin
    from ..dependencies import get_db
    from ..db.models.project import Tiers
    from ..db.models.admin_audit_log import AdminAuditLog
    from ..services.admin_coverage import db_coverage
    from ..services.admin_metrics import (
        current_period_start,
        get_usd_brl_rate,
        metrics_emails,
        metrics_ia,
        metrics_overview,
        metrics_parliamentarians,
        metrics_sections,
        metrics_tools,
        metrics_user_detail,
        metrics_users,
    )
except ImportError:  # execução dentro de api/
    from security import require_ghost_admin
    from dependencies import get_db
    from db.models.project import Tiers
    from db.models.admin_audit_log import AdminAuditLog
    from services.admin_coverage import db_coverage
    from services.admin_metrics import (
        current_period_start,
        get_usd_brl_rate,
        metrics_emails,
        metrics_ia,
        metrics_overview,
        metrics_parliamentarians,
        metrics_sections,
        metrics_tools,
        metrics_user_detail,
        metrics_users,
    )

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/whoami")
def whoami(admin_email: str = Depends(require_ghost_admin)) -> dict:
    """Valida o gate ponta a ponta: só admin autenticado chega aqui."""
    return {"email": admin_email, "is_admin": True}


class TierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tier_name_debug: str
    product_id: str
    detalhes: dict[str, Any]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TierDetailsUpdate(BaseModel):
    # preco_mensal NÃO é editável aqui: vem do Ghost (ghost_tiers_sync). Idem
    # tier_name_debug. O painel os exibe como só-leitura.
    qtd_termos: Optional[int] = Field(default=None, ge=0)
    qtd_termos_camara: Optional[int] = Field(default=None, ge=0)
    qtd_termos_senado: Optional[int] = Field(default=None, ge=0)
    qtd_consultas_ia_mes: Optional[int] = Field(default=None, ge=0)
    qtd_consultas_ia_semana: Optional[int] = Field(default=None, ge=0)
    periodicidade_email: Optional[list[str]] = None
    orgao: Optional[list[str]] = None


def _log_admin_action(
    db: Session,
    *,
    admin_email: str,
    action: str,
    entity: str,
    entity_id: str,
    before: Any,
    after: Any,
) -> None:
    db.add(
        AdminAuditLog(
            admin_email=admin_email,
            action=action,
            entity=entity,
            entity_id=entity_id,
            before=json.dumps(before, ensure_ascii=False),
            after=json.dumps(after, ensure_ascii=False),
        )
    )


@router.get("/tiers", response_model=list[TierOut])
def list_tiers(
    db: Session = Depends(get_db),
    _admin: str = Depends(require_ghost_admin),
) -> list[Tiers]:
    stmt = select(Tiers).where(Tiers.deleted_at.is_(None)).order_by(Tiers.id)
    return list(db.execute(stmt).scalars().all())


@router.put("/tiers/{tier_id}", response_model=TierOut)
def update_tier(
    tier_id: int,
    payload: TierDetailsUpdate,
    db: Session = Depends(get_db),
    admin_email: str = Depends(require_ghost_admin),
) -> Tiers:
    tier = db.get(Tiers, tier_id)
    if tier is None or tier.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tier não encontrado.")

    before = dict(tier.detalhes or {})
    updates = payload.model_dump(exclude_unset=True)
    new_detalhes = dict(before)
    new_detalhes.update(updates)
    tier.detalhes = new_detalhes

    _log_admin_action(
        db,
        admin_email=admin_email,
        action="update_tier",
        entity="tiers",
        entity_id=str(tier_id),
        before=before,
        after=new_detalhes,
    )
    db.commit()
    db.refresh(tier)
    return tier


@router.get("/metrics/overview")
def metrics_overview_route(
    db: Session = Depends(get_db),
    _admin: str = Depends(require_ghost_admin),
) -> dict[str, Any]:
    return metrics_overview(db, current_period_start(), get_usd_brl_rate(db))


@router.get("/metrics/users")
def metrics_users_route(
    limit: Optional[int] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    _admin: str = Depends(require_ghost_admin),
) -> dict[str, Any]:
    period = current_period_start()
    rate = get_usd_brl_rate(db)
    return {
        "period_start": period.isoformat(),
        "usd_brl_rate": round(rate, 4),
        "users": metrics_users(db, period, rate, limit=limit, search=search),
    }


@router.get("/metrics/tools")
def metrics_tools_route(
    db: Session = Depends(get_db),
    _admin: str = Depends(require_ghost_admin),
) -> dict[str, Any]:
    return {"tools": metrics_tools(db)}


@router.get("/metrics/sections")
def metrics_sections_route(
    db: Session = Depends(get_db),
    _admin: str = Depends(require_ghost_admin),
) -> dict[str, Any]:
    return {"sections": metrics_sections(db)}


@router.get("/metrics/parliamentarians")
def metrics_parliamentarians_route(
    limit: int = 20,
    db: Session = Depends(get_db),
    _admin: str = Depends(require_ghost_admin),
) -> dict[str, Any]:
    return metrics_parliamentarians(db, limit=limit)


@router.get("/metrics/ia")
def metrics_ia_route(
    db: Session = Depends(get_db),
    _admin: str = Depends(require_ghost_admin),
) -> dict[str, Any]:
    return metrics_ia(db, current_period_start(), get_usd_brl_rate(db))


@router.get("/metrics/emails")
def metrics_emails_route(
    db: Session = Depends(get_db),
    _admin: str = Depends(require_ghost_admin),
) -> dict[str, Any]:
    return metrics_emails(db)


@router.get("/coverage")
def coverage_route(
    db: Session = Depends(get_db),
    _admin: str = Depends(require_ghost_admin),
) -> dict[str, Any]:
    return db_coverage(db)


@router.get("/metrics/users/{projeto_id}")
def metrics_user_detail_route(
    projeto_id: int,
    db: Session = Depends(get_db),
    _admin: str = Depends(require_ghost_admin),
) -> dict[str, Any]:
    detail = metrics_user_detail(
        db, projeto_id, current_period_start(), get_usd_brl_rate(db)
    )
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    return detail
