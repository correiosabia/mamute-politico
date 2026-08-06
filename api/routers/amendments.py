"""Rotas de emendas parlamentares orcamentarias (CS-17).

Nao confundir com emenda a proposicao: aqui e destinacao de verba do orcamento
federal, coletada do Portal da Transparencia.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, field_serializer
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

try:
    # Execução como pacote (api.routers.amendments).
    from ..db.models.parliamentary_amendment import ParliamentaryAmendment
    from ..dependencies import get_db
except (ImportError, ValueError):
    # Execução local dentro de api/ sem reconhecimento de pacote.
    from db.models.parliamentary_amendment import ParliamentaryAmendment
    from dependencies import get_db

router = APIRouter(prefix="/amendments", tags=["amendments"])

AmendmentSortBy = Literal["year", "committed_value", "paid_value", "id"]
SortOrder = Literal["asc", "desc"]

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")


def _to_decimal(value: Any) -> Decimal:
    """Normaliza para Decimal com 2 casas.

    O SQLite devolve float em SUM(); o Postgres devolve Decimal. Passar por str
    evita a expansao binaria de Decimal(float).
    """
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value.quantize(CENTS)
    return Decimal(str(value)).quantize(CENTS)


class AmendmentOut(BaseModel):
    """Emenda parlamentar serializada."""

    id: int
    amendment_code: str
    year: Optional[int] = None
    amendment_number: Optional[str] = None
    amendment_type: Optional[str] = None
    author_name_raw: Optional[str] = None
    parliamentarian_id: Optional[int] = None
    match_status: str
    spending_locality: Optional[str] = None
    function: Optional[str] = None
    subfunction: Optional[str] = None
    committed_value: Optional[Decimal] = None
    settled_value: Optional[Decimal] = None
    paid_value: Optional[Decimal] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("committed_value", "settled_value", "paid_value")
    def _serialize_money(self, value: Optional[Decimal]) -> Optional[str]:
        # String, nunca float: dinheiro publico nao pode perder centavo em
        # ponto flutuante.
        return None if value is None else str(value)


class AmendmentSummaryOut(BaseModel):
    """Totais anuais de emendas de um parlamentar."""

    year: Optional[int] = None
    count: int
    committed_total: Decimal
    paid_total: Decimal

    @field_serializer("committed_total", "paid_total")
    def _serialize_money(self, value: Decimal) -> str:
        return str(value)


# `/summary` vem antes de `/` para nao ser capturada por uma rota de path param
# que venha a ser acrescentada depois.
@router.get("/summary", response_model=AmendmentSummaryOut)
def get_amendments_summary(
    parliamentarian_id: int = Query(..., description="Parlamentar dono das emendas"),
    year: Optional[int] = Query(None, description="Ano civil; omitido soma todos"),
    db: Session = Depends(get_db),
) -> AmendmentSummaryOut:
    """Totais de valor empenhado e pago de um parlamentar, por ano."""
    stmt = select(
        func.count(ParliamentaryAmendment.id),
        func.sum(ParliamentaryAmendment.committed_value),
        func.sum(ParliamentaryAmendment.paid_value),
    ).where(ParliamentaryAmendment.parliamentarian_id == parliamentarian_id)

    if year is not None:
        stmt = stmt.where(ParliamentaryAmendment.year == year)

    count, committed, paid = db.execute(stmt).one()

    return AmendmentSummaryOut(
        year=year,
        count=count or 0,
        committed_total=_to_decimal(committed),
        paid_total=_to_decimal(paid),
    )


@router.get("/", response_model=List[AmendmentOut])
def list_amendments(
    parliamentarian_id: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort_by: AmendmentSortBy = Query("committed_value"),
    sort_order: SortOrder = Query("desc"),
    db: Session = Depends(get_db),
) -> List[AmendmentOut]:
    """Lista emendas, opcionalmente filtradas por parlamentar e ano."""
    stmt = select(ParliamentaryAmendment)

    if parliamentarian_id is not None:
        stmt = stmt.where(
            ParliamentaryAmendment.parliamentarian_id == parliamentarian_id
        )
    if year is not None:
        stmt = stmt.where(ParliamentaryAmendment.year == year)

    column = getattr(ParliamentaryAmendment, sort_by)
    direction = desc if sort_order == "desc" else asc
    # Desempate por id mantem a paginacao estavel quando o criterio empata.
    stmt = stmt.order_by(direction(column), ParliamentaryAmendment.id)
    stmt = stmt.limit(limit).offset(offset)

    return [AmendmentOut.model_validate(row) for row in db.execute(stmt).scalars()]
