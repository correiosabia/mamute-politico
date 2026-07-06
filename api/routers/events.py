"""Ingesta de eventos de uso do app (page views). Auth de membro."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from ..security import verify_token
    from ..dependencies import get_db
    from ..db.models.usage_event import UsageEvent
except ImportError:  # execução dentro de api/
    from security import verify_token
    from dependencies import get_db
    from db.models.usage_event import UsageEvent

router = APIRouter(prefix="/events", tags=["events"])

# page_view e section_view vêm do cliente; favoritos são logados server-side.
_ALLOWED_TYPES = {"page_view", "section_view"}


class EventIn(BaseModel):
    type: str
    page: Optional[str] = None
    section: Optional[str] = None


class EventsBatch(BaseModel):
    events: list[EventIn]


def _resolve_projeto_id(db: Session, email: Optional[str]) -> Optional[int]:
    if not email:
        return None
    row = db.execute(
        text(
            "SELECT id FROM projetos WHERE lower(email) = :e "
            "AND deleted_at IS NULL LIMIT 1"
        ),
        {"e": email},
    ).first()
    return int(row[0]) if row else None


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
def ingest_events(
    batch: EventsBatch,
    payload: dict = Depends(verify_token),
    db: Session = Depends(get_db),
) -> Response:
    email = (payload.get("sub") or "").strip().lower() or None
    projeto_id = _resolve_projeto_id(db, email)
    for event in batch.events:
        if event.type not in _ALLOWED_TYPES:
            continue
        db.add(
            UsageEvent(
                projeto_id=projeto_id,
                email=email,
                event_type=event.type,
                page=event.page,
                section=event.section,
            )
        )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
