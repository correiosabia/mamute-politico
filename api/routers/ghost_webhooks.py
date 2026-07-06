"""Webhooks recebidos do Ghost."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

try:
    # Execução como pacote (api.routers.ghost_webhooks).
    from ..dependencies import get_db
    from ..services.ghost_member_sync import (
        GhostMemberProjectSyncResult,
        normalize_email,
        soft_delete_member_project,
        sync_member_project,
    )
    from ..services.ghost_admin import fetch_ghost_member_by_email_from_env
    from ..services.ghost_webhook_security import verify_ghost_signature
except (ImportError, ValueError):  # pragma: no cover - caminho Docker/top-level.
    from dependencies import get_db
    from services.ghost_member_sync import (
        GhostMemberProjectSyncResult,
        normalize_email,
        soft_delete_member_project,
        sync_member_project,
    )
    from services.ghost_admin import fetch_ghost_member_by_email_from_env
    from services.ghost_webhook_security import verify_ghost_signature


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/ghost", tags=["webhooks"])


class GhostWebhookMemberResponse(BaseModel):
    action: str
    email: str | None = None
    project_id: int | None = None
    product_id: str | None = None
    reason: str | None = None


def _webhook_secret() -> str:
    return os.getenv("GHOST_WEBHOOK_SECRET", "")


def _webhook_signature_tolerance_seconds() -> int:
    raw_value = os.getenv("GHOST_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS", "300")
    try:
        return int(raw_value)
    except ValueError:
        return 300


def _member_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    member = payload.get("member")
    if not isinstance(member, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload sem objeto member.",
        )

    current = member.get("current") or {}
    previous = member.get("previous") or {}
    if not isinstance(current, dict) or not isinstance(previous, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload member.current/member.previous inválido.",
        )
    return current, previous


def _response(result: GhostMemberProjectSyncResult) -> GhostWebhookMemberResponse:
    return GhostWebhookMemberResponse(**asdict(result))


def _enrich_current_member(current: dict[str, Any]) -> dict[str, Any]:
    email = normalize_email(current.get("email"))
    if email is None:
        return current
    try:
        enriched = fetch_ghost_member_by_email_from_env(email)
    except Exception:
        logger.warning("Falha ao enriquecer member Ghost via Admin API.", exc_info=True)
        return current
    if enriched is None:
        return current
    return enriched


@router.post(
    "/members",
    response_model=GhostWebhookMemberResponse,
    summary="Recebe eventos member.* do Ghost",
)
async def receive_ghost_member_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> GhostWebhookMemberResponse:
    secret = _webhook_secret()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook do Ghost sem segredo configurado.",
        )

    raw_body = await request.body()
    verification = verify_ghost_signature(
        raw_body,
        request.headers.get("x-ghost-signature"),
        secret,
        tolerance_seconds=_webhook_signature_tolerance_seconds(),
    )
    if not verification.valid:
        logger.warning("Webhook Ghost recusado: %s", verification.reason)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Assinatura inválida.",
        )

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload JSON inválido.",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload precisa ser um objeto JSON.",
        )

    current, previous = _member_payload(payload)
    if current.get("email"):
        return _response(sync_member_project(db, _enrich_current_member(current), previous))
    if previous.get("email"):
        return _response(soft_delete_member_project(db, previous))

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Payload member.* sem e-mail sincronizável.",
    )


__all__ = ["router"]
