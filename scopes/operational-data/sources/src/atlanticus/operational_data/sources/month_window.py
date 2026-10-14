from __future__ import annotations

from datetime import UTC, datetime

from atlanticus.operational_data.core import (
    DataSource,
    TimeWindow,
    TimeWindowUnit,
    normalize_utc_second,
)

_FABRICA_SOURCES = frozenset({DataSource.FABRICA_PLANES, DataSource.FABRICA_KPIS})


def time_window_start(*, source: DataSource, window: TimeWindow, as_of: datetime) -> datetime:
    if source not in _FABRICA_SOURCES or window.unit is not TimeWindowUnit.MONTHS:
        return window.start_from(as_of)
    timestamp = normalize_utc_second(as_of, field_name='as_of')
    month_index = timestamp.year * 12 + timestamp.month - window.value
    year, zero_based_month = divmod(month_index, 12)
    return datetime(year, zero_based_month + 1, 1, tzinfo=UTC)
