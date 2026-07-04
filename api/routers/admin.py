"""Rotas administrativas — gated por require_ghost_admin (404 para não-admin)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

try:
    from ..security import require_ghost_admin
except ImportError:  # execução dentro de api/
    from security import require_ghost_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/whoami")
def whoami(admin_email: str = Depends(require_ghost_admin)) -> dict:
    """Valida o gate ponta a ponta: só admin autenticado chega aqui."""
    return {"email": admin_email, "is_admin": True}
