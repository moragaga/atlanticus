from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.time_series import TimeSeriesPoint, TimeSeriesValues

from .definitions import ALIMENTADO_TRENDS
from .models import AlimentadoTrendReading

_STEP_SECONDS = 120


def map_tendencia_alimentado_store(store_data: object) -> tuple[AlimentadoTrendReading, ...]:
    data = store_data if isinstance(store_data, Mapping) else None
    latest = data.get('latest') if data is not None else None
    timeseries = data.get('timeseries') if data is not None else None
    return tuple(
        AlimentadoTrendReading(
            definition=definition,
            current=_current(latest, definition.kpi_key),
            history=_history(timeseries, definition.kpi_key),
        )
        for definition in ALIMENTADO_TRENDS
    )


def _current(latest: object, key: str) -> DisplayValue:
    if latest is None:
        return DisplayValue.not_mapped()
    if not isinstance(latest, Mapping) or not isinstance(latest.get('values'), Mapping):
        return DisplayValue.invalid()
    values = latest['values']
    decoded = decode_kpi_latest_value(values.get(key), present=key in values)
    if decoded.state is KpiLatestValueState.NOT_MAPPED:
        return DisplayValue.not_mapped()
    if decoded.state is KpiLatestValueState.MISSING:
        return DisplayValue.empty()
    if decoded.state is KpiLatestValueState.ERROR:
        return DisplayValue.error()
    if decoded.state is not KpiLatestValueState.OK:
        return DisplayValue.invalid()
    if decoded.value_kind != 'value' or isinstance(decoded.value, bool):
        return DisplayValue.invalid()
    if not isinstance(decoded.value, str | int | float):
        return DisplayValue.invalid()
    text = str(decoded.value).strip()
    try:
        _numeric(text)
    except (ValueError, OverflowError):
        return DisplayValue.invalid()
    return DisplayValue.ok(text) if text else DisplayValue.invalid()


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError('Time series UTC timestamp must be a non-empty ISO string')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Time series timestamp must be timezone-aware')
    return parsed.astimezone(UTC)


def _numeric(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError('Time series sample must be numeric or null')
    text = str(value).strip().replace(',', '.')
    number = float(text)
    if not math.isfinite(number):
        raise ValueError('Time series sample must be finite')
    return number


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
        if value_type == 'boolean':
            raise ValueError('Boolean series cannot be drawn as numeric trends')
        if value_type is None and any(value is not None for value in values):
            raise ValueError('Time series values require a value_type')
        points = tuple(
            TimeSeriesPoint(start + timedelta(seconds=step * (index + 1)), _numeric(value))
            for index, value in enumerate(values)
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return TimeSeriesValues(DisplayStatus.INVALID)
    if not any(point.value is not None for point in points):
        return TimeSeriesValues(DisplayStatus.EMPTY)
    return TimeSeriesValues(DisplayStatus.OK, points)
