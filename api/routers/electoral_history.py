"""Rotas de timeline eleitoral de politicos e candidatos (CS-54).

A tabela electoral_history e populada pelo tse_crawler a partir da
DivulgaCandContas; aqui e so leitura. A lista completa de bens (`assets`) e
pesada e so trafega com `include_assets=true` — o payload padrao leva apenas
o total declarado.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_serializer
from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    # Execução como pacote (api.routers.electoral_history).
    from ..db.models.candidacy import Candidacy
    from ..db.models.electoral_history import ElectoralHistory
    from ..db.models.parliamentarian import Parliamentarian
    from ..dependencies import get_db
except (ImportError, ValueError):
    # Execução local dentro de api/ sem reconhecimento de pacote.
    from db.models.candidacy import Candidacy
    from db.models.electoral_history import ElectoralHistory
    from db.models.parliamentarian import Parliamentarian
    from dependencies import get_db

router = APIRouter(tags=["electoral-history"])


class ElectoralHistoryEntryOut(BaseModel):
    """Uma disputa eleitoral na linha do tempo do politico."""

    year: int
    office: Optional[str] = None
    state: Optional[str] = None
    locality: Optional[str] = None
    party: Optional[str] = None
    ballot_name: Optional[str] = None
    result: Optional[str] = None
    declared_assets: Optional[Decimal] = None
    assets_count: Optional[int] = None
    source_link: Optional[str] = None
    assets: Optional[Any] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("declared_assets")
    def _serialize_money(self, value: Optional[Decimal]) -> Optional[str]:
        # String, nunca float: patrimonio declarado nao pode perder centavo
        # em ponto flutuante (mesma regra das emendas).
        return None if value is None else str(value)


class ElectoralHistoryOut(BaseModel):
    entries: List[ElectoralHistoryEntryOut]


def _timeline(
    db: Session, where_clause: Any, include_assets: bool
) -> ElectoralHistoryOut:
    stmt = (
        select(ElectoralHistory)
        .where(where_clause)
        .order_by(ElectoralHistory.election_year.desc(), ElectoralHistory.id)
    )
    entries = [
        ElectoralHistoryEntryOut(
            year=row.election_year,
            office=row.office,
            state=row.state,
            locality=row.locality,
            party=row.party,
            ballot_name=row.ballot_name,
            result=row.result,
            declared_assets=row.declared_assets,
            assets_count=row.assets_count,
            source_link=row.source_link,
            assets=row.assets if include_assets else None,
        )
        for row in db.execute(stmt).scalars()
    ]
    return ElectoralHistoryOut(entries=entries)


@router.get(
    "/parliamentarians/{parliamentarian_id}/electoral-history",
    response_model=ElectoralHistoryOut,
    response_model_exclude_none=True,
)
def get_parliamentarian_electoral_history(
    parliamentarian_id: int,
    include_assets: bool = Query(False, description="Inclui a lista de bens"),
    db: Session = Depends(get_db),
) -> ElectoralHistoryOut:
    """Linha do tempo eleitoral de um parlamentar."""
    if db.get(Parliamentarian, parliamentarian_id) is None:
        raise HTTPException(status_code=404, detail="Parlamentar não encontrado")
    return _timeline(
        db,
        ElectoralHistory.parliamentarian_id == parliamentarian_id,
        include_assets,
    )


@router.get(
    "/candidacies/{candidacy_id}/electoral-history",
    response_model=ElectoralHistoryOut,
    response_model_exclude_none=True,
)
def get_candidacy_electoral_history(
    candidacy_id: int,
    include_assets: bool = Query(False, description="Inclui a lista de bens"),
    db: Session = Depends(get_db),
) -> ElectoralHistoryOut:
    """Linha do tempo eleitoral pela candidatura 2026."""
    if db.get(Candidacy, candidacy_id) is None:
        raise HTTPException(status_code=404, detail="Candidatura não encontrada")
    return _timeline(
        db, ElectoralHistory.candidacy_id == candidacy_id, include_assets
    )
