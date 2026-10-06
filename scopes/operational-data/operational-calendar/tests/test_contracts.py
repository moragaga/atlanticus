from __future__ import annotations

from atlanticus.operational_data.calendar import MINE_CALENDAR, OperationalCalendarResolver


def test_operational_calendar_implements_resolver_contract() -> None:
    assert isinstance(MINE_CALENDAR, OperationalCalendarResolver)
