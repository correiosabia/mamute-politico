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
except ImportError:  # execução dentro de api/
    from security import require_ghost_admin
    from dependencies import get_db
    from db.models.project import Tiers
    from db.models.admin_audit_log import AdminAuditLog

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
    qtd_termos: Optional[int] = Field(default=None, ge=0)
    qtd_consultas_ia_mes: Optional[int] = Field(default=None, ge=0)
    qtd_email: Optional[int] = Field(default=None, ge=0)
    periodicidade_email: Optional[list[str]] = None
    orgao: Optional[list[str]] = None
    preco_mensal: Optional[float] = Field(default=None, ge=0)


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
