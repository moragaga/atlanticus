from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.time_series import TimeSeriesPoint, TimeSeriesValues

from .definitions import ALIMENTADO_TRENDS
from .models import AlimentadoTrendReading

_STEP_SECONDS = 120


def map_tendencia_alimentado_readings(
    readings: Mapping[str, DisplayValue], timeseries: object
) -> tuple[AlimentadoTrendReading, ...]:
    return tuple(
        AlimentadoTrendReading(
            definition=definition,
            current=readings[definition.kpi_key],
            history=_history(timeseries, definition.kpi_key),
        )
        for definition in ALIMENTADO_TRENDS
    )


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError('Time series UTC timestamp must be a non-empty ISO string')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Time series timestamp must be timezone-aware')
    return parsed.astimezone(UTC)


def _history(timeseries: object, key: str) -> TimeSeriesValues:
    if timeseries is None:
        return TimeSeriesValues(DisplayStatus.NOT_MAPPED)
    if not isinstance(timeseries, Mapping):
        return TimeSeriesValues(DisplayStatus.INVALID)
    raw_series = timeseries.get('series')
    if not isinstance(raw_series, Mapping):
        return TimeSeriesValues(DisplayStatus.INVALID)
    if key not in raw_series:
        return TimeSeriesValues(DisplayStatus.NOT_MAPPED)
    try:
        entry = raw_series[key]
        if not isinstance(entry, Mapping):
            raise ValueError('Time series entry must be an object')
        hours = entry['hours']
        if type(hours) is not int or not 1 <= hours <= 24:
            raise ValueError('Time series hours must be 1..24')
        step = timeseries['step_seconds']
        if type(step) is not int or step != _STEP_SECONDS:
            raise ValueError('Time series step_seconds is unsupported')
        start = _utc(entry['start_utc'])
        end = _utc(entry['end_utc'])
        if end != _utc(timeseries['end_utc']) or start != end - timedelta(hours=hours):
            raise ValueError('Time series bounds are inconsistent')
        values = entry['values']
        if not isinstance(values, list) or len(values) != hours * 3600 // step:
            raise ValueError('Time series samples count is inconsistent')
        value_type = entry['value_type']
        if value_type not in {'text', 'integer', 'float', 'boolean', None}:
            raise ValueError('Time series value_type is invalid')
        if value_type not in {'integer', 'float'} and any(value is not None for value in values):
            raise ValueError('Non-numeric series cannot be drawn as numeric trends')
        points = tuple(
            TimeSeriesPoint(start + timedelta(seconds=step * (index + 1)), value)
            for index, value in enumerate(values)
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return TimeSeriesValues(DisplayStatus.INVALID)
    return TimeSeriesValues(DisplayStatus.OK, points)
