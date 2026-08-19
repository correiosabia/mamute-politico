"""Rotas de gastos da cota parlamentar (CS-57).

CEAP da Camara + CEAPS do Senado, uma linha por despesa, discriminada por
`house`. Nao confundir com emendas: emenda e verba que o parlamentar destina;
a cota e verba que ele gasta com o proprio mandato.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_serializer
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

try:
    # Execução como pacote (api.routers.expenses).
    from ..db.models.parliamentary_expense import ParliamentaryExpense
    from ..dependencies import get_db
    from ..feature_gate import PREVIEW_ROWS, FeatureAccess, cota_access
except (ImportError, ValueError):
    # Execução local dentro de api/ sem reconhecimento de pacote.
    from db.models.parliamentary_expense import ParliamentaryExpense
    from dependencies import get_db
    from feature_gate import PREVIEW_ROWS, FeatureAccess, cota_access

router = APIRouter(prefix="/expenses", tags=["expenses"])

ExpenseSortBy = Literal["year", "month", "net_value", "id"]
SortOrder = Literal["asc", "desc"]

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")

TOP_SUPPLIERS = 10


def _to_decimal(value: Any) -> Decimal:
    """Normaliza para Decimal com 2 casas (SQLite devolve float em SUM())."""
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value.quantize(CENTS)
    return Decimal(str(value)).quantize(CENTS)


class ExpenseOut(BaseModel):
    """Gasto da cota parlamentar serializado."""

    id: int
    house: str
    source_key: str
    parliamentarian_id: Optional[int] = None
    year: int
    month: int
    expense_type: str
    supplier_name: Optional[str] = None
    supplier_id: Optional[str] = None
    document_number: Optional[str] = None
    document_date: Optional[date] = None
    details: Optional[str] = None
    document_value: Optional[Decimal] = None
    glosa_value: Optional[Decimal] = None
    net_value: Decimal
    document_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("document_value", "glosa_value")
    def _serialize_money(self, value: Optional[Decimal]) -> Optional[str]:
        # String, nunca float: dinheiro publico nao pode perder centavo em
        # ponto flutuante.
        return None if value is None else str(value)

    @field_serializer("net_value")
    def _serialize_net(self, value: Decimal) -> str:
        return str(value)


class MonthlyTypeTotalOut(BaseModel):
    """Total de um tipo de despesa em um mes — celula do grafico empilhado."""

    month: int
    expense_type: str
    total: Decimal

    @field_serializer("total")
    def _serialize_money(self, value: Decimal) -> str:
        return str(value)


class TopSupplierOut(BaseModel):
    """Fornecedor agregado do ano, ordenado por total recebido."""

    supplier_name: Optional[str] = None
    supplier_id: Optional[str] = None
    total: Decimal
    count: int

    @field_serializer("total")
    def _serialize_money(self, value: Decimal) -> str:
        return str(value)


class ExpenseSummaryOut(BaseModel):
    """Resumo anual de cota de um parlamentar: mensal por tipo + fornecedores."""

    year: Optional[int] = None
    count: int
    total: Decimal
    monthly: List[MonthlyTypeTotalOut]
    top_suppliers: List[TopSupplierOut]

    @field_serializer("total")
    def _serialize_money(self, value: Decimal) -> str:
        return str(value)


# `/summary` vem antes de `/` para nao ser capturada por uma rota de path
# param que venha a ser acrescentada depois.
@router.get("/summary", response_model=ExpenseSummaryOut)
def get_expenses_summary(
    parliamentarian_id: int = Query(..., description="Parlamentar dono dos gastos"),
    year: Optional[int] = Query(None, description="Ano civil; omitido soma todos"),
    db: Session = Depends(get_db),
    access: FeatureAccess = Depends(cota_access),
) -> ExpenseSummaryOut:
    """Serie mensal por tipo de despesa + top fornecedores de um parlamentar."""
    if not access.full:
        # O agregado E o produto: nao ha previa de um grafico. O front nem
        # chama esta rota com o recurso bloqueado — mostra o cadeado.
        raise HTTPException(
            status_code=403, detail="Recurso não disponível no seu plano."
        )

    base_where = [ParliamentaryExpense.parliamentarian_id == parliamentarian_id]
    if year is not None:
        base_where.append(ParliamentaryExpense.year == year)

    count, total = db.execute(
        select(
            func.count(ParliamentaryExpense.id),
            func.sum(ParliamentaryExpense.net_value),
        ).where(*base_where)
    ).one()

    monthly_rows = db.execute(
        select(
            ParliamentaryExpense.month,
            ParliamentaryExpense.expense_type,
            func.sum(ParliamentaryExpense.net_value),
        )
        .where(*base_where)
        .group_by(ParliamentaryExpense.month, ParliamentaryExpense.expense_type)
        .order_by(ParliamentaryExpense.month, ParliamentaryExpense.expense_type)
    ).all()

    supplier_rows = db.execute(
        select(
            ParliamentaryExpense.supplier_name,
            ParliamentaryExpense.supplier_id,
            func.sum(ParliamentaryExpense.net_value).label("total"),
            func.count(ParliamentaryExpense.id),
        )
        .where(*base_where)
        .where(ParliamentaryExpense.supplier_name.isnot(None))
        .group_by(
            ParliamentaryExpense.supplier_name, ParliamentaryExpense.supplier_id
        )
        .order_by(desc("total"))
        .limit(TOP_SUPPLIERS)
    ).all()

    return ExpenseSummaryOut(
        year=year,
        count=count or 0,
        total=_to_decimal(total),
        monthly=[
            MonthlyTypeTotalOut(
                month=month, expense_type=expense_type, total=_to_decimal(value)
            )
            for month, expense_type, value in monthly_rows
        ],
        top_suppliers=[
            TopSupplierOut(
                supplier_name=name,
                supplier_id=supplier_id,
                total=_to_decimal(value),
                count=n,
            )
            for name, supplier_id, value, n in supplier_rows
        ],
    )


@router.get("/", response_model=List[ExpenseOut])
def list_expenses(
    parliamentarian_id: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None, ge=1, le=12),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort_by: ExpenseSortBy = Query("net_value"),
    sort_order: SortOrder = Query("desc"),
    db: Session = Depends(get_db),
    access: FeatureAccess = Depends(cota_access),
) -> List[ExpenseOut]:
    """Lista gastos, opcionalmente filtrados por parlamentar, ano e mes."""
    if not access.full:
        # PREVIA (CS-58): mantem o contexto da tela, mas pina ordenacao e
        # corte no servidor. Honrar limit/offset/sort aqui viraria oraculo de
        # extracao via paginacao.
        limit = PREVIEW_ROWS
        offset = 0
        sort_by = "net_value"
        sort_order = "desc"

    stmt = select(ParliamentaryExpense)
    if parliamentarian_id is not None:
        stmt = stmt.where(
            ParliamentaryExpense.parliamentarian_id == parliamentarian_id
        )
    if year is not None:
        stmt = stmt.where(ParliamentaryExpense.year == year)
    if month is not None:
        stmt = stmt.where(ParliamentaryExpense.month == month)

    column = getattr(ParliamentaryExpense, sort_by)
    direction = desc if sort_order == "desc" else asc
    # Desempate por id mantem a paginacao estavel quando o criterio empata.
    stmt = stmt.order_by(direction(column), ParliamentaryExpense.id)
    stmt = stmt.limit(limit).offset(offset)

    return [
        ExpenseOut.model_validate(row) for row in db.execute(stmt).scalars()
    ]
