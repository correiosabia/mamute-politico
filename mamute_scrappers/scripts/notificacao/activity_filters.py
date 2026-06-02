"""Filtros de período para stats e destaques (alinhados ao dashboard da API)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, and_, cast, func, or_
from sqlalchemy.sql.elements import ColumnElement

from mamute_scrappers.db.models import Proposition

from .dates import extract_vote_date_from_proposition


def _decisao_date_expr():
    return cast(
        Proposition.details["decisao_destino"]["Decisao"]["Data"].astext,
        Date,
    )


def vote_on_sql() -> ColumnElement:
    """Data legislativa da votação (decisão da proposição ou apresentação)."""
    return func.coalesce(_decisao_date_expr(), Proposition.presentation_date)


def proposition_in_period(
    range_start: date,
    range_end: date,
    range_start_dt: datetime,
    range_end_dt_exclusive: datetime,
    *,
    include_ingested: bool = False,
) -> ColumnElement:
    """
    Proposição no período por data de apresentação.

    Com `include_ingested=True` (relatório diário), inclui também proposições
    indexadas no Mamute no intervalo, mesmo com apresentação anterior.
    """
    by_presentation = and_(
        Proposition.presentation_date.is_not(None),
        Proposition.presentation_date >= range_start,
        Proposition.presentation_date <= range_end,
    )
    if not include_ingested:
        return by_presentation
    by_ingest = and_(
        Proposition.created_at >= range_start_dt,
        Proposition.created_at < range_end_dt_exclusive,
    )
    return or_(by_presentation, by_ingest)


def vote_in_period(
    range_start: date,
    range_end: date,
) -> ColumnElement:
    """Votação cuja data legislativa cai no intervalo."""
    vote_on = vote_on_sql()
    return and_(
        vote_on.is_not(None),
        vote_on >= range_start,
        vote_on <= range_end,
    )


def vote_occurred_at(
    *,
    prop_details,
    presentation_date: date | None,
) -> date | None:
    """Data exibida/ordenada para votação (legislativa)."""
    return extract_vote_date_from_proposition(prop_details, presentation_date)
