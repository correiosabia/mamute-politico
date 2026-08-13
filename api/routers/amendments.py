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
    from ..db.models.amendment_action_plan import AmendmentActionPlan
    from ..db.models.parliamentary_amendment import ParliamentaryAmendment
    from ..dependencies import get_db
except (ImportError, ValueError):
    # Execução local dentro de api/ sem reconhecimento de pacote.
    from db.models.amendment_action_plan import AmendmentActionPlan
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

    # Prestacao de contas agregada dos planos de acao (so emendas Pix tem).
    # Zero, e nunca null, para emenda sem plano: a tela distingue "nenhum
    # plano" de "dado ausente" pelo tipo da emenda, nao por null.
    planos_total: int = 0
    planos_com_prestacao: int = 0
    valor_executado_total: Decimal = ZERO

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("committed_value", "settled_value", "paid_value")
    def _serialize_money(self, value: Optional[Decimal]) -> Optional[str]:
        # String, nunca float: dinheiro publico nao pode perder centavo em
        # ponto flutuante.
        return None if value is None else str(value)

    @field_serializer("valor_executado_total")
    def _serialize_total(self, value: Decimal) -> str:
        return str(value)


class ActionPlanOut(BaseModel):
    """Plano de acao de uma emenda Pix — um por ente beneficiario."""

    id_plano_acao: int
    codigo_plano_acao: Optional[str] = None
    amendment_code: Optional[str] = None
    # O ano do plano e o que permite a tela dizer "prazo aberto" em vez de
    # "nao prestou contas". Sem ele, ausencia de prestacao vira acusacao.
    ano: Optional[int] = None
    situacao: Optional[str] = None
    beneficiario_nome: Optional[str] = None
    beneficiario_cnpj: Optional[str] = None
    beneficiario_uf: Optional[str] = None
    valor_custeio: Optional[Decimal] = None
    valor_investimento: Optional[Decimal] = None
    prestacao_situacao: Optional[str] = None
    prestacao_tipo: Optional[str] = None
    prestacao_valor_executado: Optional[Decimal] = None
    prestacao_valor_pendente: Optional[Decimal] = None
    prestacao_data: Optional[str] = None
    prestacao_origem: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer(
        "valor_custeio",
        "valor_investimento",
        "prestacao_valor_executado",
        "prestacao_valor_pendente",
    )
    def _serialize_money(self, value: Optional[Decimal]) -> Optional[str]:
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
    # Subquery, e nao join direto: uma emenda Pix tem varios planos de acao
    # (mediana 8), e o join multiplicaria a linha da emenda.
    agregado = (
        select(
            AmendmentActionPlan.amendment_code.label("code"),
            func.count(AmendmentActionPlan.id_plano_acao).label("planos_total"),
            # count() de coluna ignora NULL: conta so os planos que prestaram.
            func.count(AmendmentActionPlan.prestacao_situacao).label(
                "com_prestacao"
            ),
            func.coalesce(
                func.sum(AmendmentActionPlan.prestacao_valor_executado), 0
            ).label("executado"),
        )
        .group_by(AmendmentActionPlan.amendment_code)
        .subquery()
    )

    stmt = select(
        ParliamentaryAmendment,
        func.coalesce(agregado.c.planos_total, 0),
        func.coalesce(agregado.c.com_prestacao, 0),
        func.coalesce(agregado.c.executado, 0),
    ).outerjoin(
        agregado, agregado.c.code == ParliamentaryAmendment.amendment_code
    )

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

    saida: List[AmendmentOut] = []
    for emenda, total, com_prestacao, executado in db.execute(stmt).all():
        item = AmendmentOut.model_validate(emenda)
        item.planos_total = total or 0
        item.planos_com_prestacao = com_prestacao or 0
        item.valor_executado_total = _to_decimal(executado)
        saida.append(item)
    return saida


@router.get(
    "/{amendment_code}/action-plans", response_model=List[ActionPlanOut]
)
def list_action_plans(
    amendment_code: str,
    db: Session = Depends(get_db),
) -> List[ActionPlanOut]:
    """Planos de acao (entes beneficiarios) de uma emenda Pix.

    Devolve vazio, e nao 404, para emenda sem plano: e o caso normal das
    emendas de Finalidade Definida, que sao 85% da base e nunca tem plano de
    acao — o Transferegov so publica API para transferencias especiais.
    """
    stmt = (
        select(AmendmentActionPlan)
        .where(AmendmentActionPlan.amendment_code == amendment_code)
        .order_by(
            AmendmentActionPlan.beneficiario_uf,
            AmendmentActionPlan.beneficiario_nome,
            AmendmentActionPlan.id_plano_acao,
        )
    )
    return [
        ActionPlanOut.model_validate(row) for row in db.execute(stmt).scalars()
    ]
