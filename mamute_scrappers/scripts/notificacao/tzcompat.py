"""Fuso horário compatível com Python 3.8+ (zoneinfo só existe a partir do 3.9)."""

from __future__ import annotations

from datetime import date, datetime, time

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def now_local() -> datetime:
    return datetime.now(SAO_PAULO)


def combine_local(day: date, clock: time) -> datetime:
    return datetime.combine(day, clock, tzinfo=SAO_PAULO)


def min_local() -> datetime:
    return datetime.min.replace(tzinfo=SAO_PAULO)
