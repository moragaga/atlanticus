# Versión pedagógica: Latest llega preparado; solamente STR interpreta Timeseries y valida intervalos de 120 segundos.
from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.time_series import TimeSeriesPoint, TimeSeriesValues

from .definitions import STR_TREND
from .models import StrOverviewReading

_STEP_SECONDS = 120


def map_str_overview_readings(
    readings: Mapping[str, DisplayValue], store_data: object
) -> StrOverviewReading:
    return StrOverviewReading(
        current=readings[STR_TREND.kpi_key],
        history=_history(store_data),
    )


def _history(store_data: object) -> TimeSeriesValues:
    if not isinstance(store_data, Mapping):
        return TimeSeriesValues(DisplayStatus.INVALID)
    timeseries = store_data.get('timeseries')
    if timeseries is None:
        return TimeSeriesValues(DisplayStatus.NOT_MAPPED)
    if not isinstance(timeseries, Mapping):
        return TimeSeriesValues(DisplayStatus.INVALID)
    series = timeseries.get('series')
    if not isinstance(series, Mapping):
        return TimeSeriesValues(DisplayStatus.INVALID)
    if STR_TREND.kpi_key not in series:
        return TimeSeriesValues(DisplayStatus.NOT_MAPPED)
    try:
        entry = series[STR_TREND.kpi_key]
        if not isinstance(entry, Mapping):
            raise ValueError('STR time series entry must be an object')
        hours = entry['hours']
        step = timeseries['step_seconds']
        if type(hours) is not int or not 1 <= hours <= 24:
            raise ValueError('STR time series hours must be between 1 and 24')
        if type(step) is not int or step != _STEP_SECONDS:
            raise ValueError('STR time series step is unsupported')
        start = _utc(entry['start_utc'])
        end = _utc(entry['end_utc'])
        if end != _utc(timeseries['end_utc']) or start != end - timedelta(hours=hours):
            raise ValueError('STR time series bounds are inconsistent')
        values = entry['values']
        if not isinstance(values, list) or len(values) != hours * 3600 // step:
            raise ValueError('STR time series samples count is inconsistent')
        value_type = entry['value_type']
        if value_type not in {'integer', 'float', None}:
            raise ValueError('STR time series values must be numeric')
        if value_type is None and any(value is not None for value in values):
            raise ValueError('STR time series values require numeric type')
        points = tuple(
            TimeSeriesPoint(start + timedelta(seconds=step * (index + 1)), value)
            for index, value in enumerate(values)
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return TimeSeriesValues(DisplayStatus.INVALID)
    return TimeSeriesValues(DisplayStatus.OK, points)


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError('STR time series timestamp must be an ISO string')
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('STR time series timestamp must be timezone-aware')
    return stamp.astimezone(UTC)
