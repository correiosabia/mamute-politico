from __future__ import annotations

from datetime import date, datetime

from api.routers import projects


def test_subtract_months_clamps_to_last_valid_day() -> None:
    assert projects._subtract_months(date(2026, 5, 31), 3) == date(2026, 2, 28)


def test_last_three_months_range_uses_sao_paulo_calendar(monkeypatch) -> None:
    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 5, 25, 17, 10, tzinfo=tz)

        combine = staticmethod(datetime.combine)

    monkeypatch.setattr(projects, "datetime", FixedDateTime)

    range_start, range_end, range_start_dt, range_end_dt_exclusive = (
        projects._last_three_months_range_sao_paulo()
    )

    assert range_start == date(2026, 2, 25)
    assert range_end == date(2026, 5, 25)
    assert range_start_dt.isoformat() == "2026-02-25T00:00:00-03:00"
    assert range_end_dt_exclusive.isoformat() == "2026-05-26T00:00:00-03:00"
