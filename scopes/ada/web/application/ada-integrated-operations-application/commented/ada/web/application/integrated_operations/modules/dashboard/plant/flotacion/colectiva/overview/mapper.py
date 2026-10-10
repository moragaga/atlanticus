from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.time_series import TimeSeriesPoint, TimeSeriesValues

from .definitions import COLECTIVA_INDICATORS, COLECTIVA_TREND
from .models import ColectivaIndicatorReading, ColectivaOverviewReading

_STEP_SECONDS = 120


# Consume Latest ya preparado y procesa Timeseries de manera independiente.
def map_colectiva_overview_readings(
    readings: Mapping[str, DisplayValue], timeseries: object
) -> ColectivaOverviewReading:
    return ColectivaOverviewReading(
        trend_current=readings[COLECTIVA_TREND.kpi_key],
        trend_history=_history_values(timeseries, COLECTIVA_TREND.kpi_key),
        indicators=tuple(
            ColectivaIndicatorReading(definition, readings[definition.kpi_key])
            for definition in COLECTIVA_INDICATORS
        ),
    )


# Valida el historial de recuperación de cobre con intervalos fijos de 120 segundos.
def _history_values(timeseries: object, key: str) -> TimeSeriesValues:
    if timeseries is None:
        return TimeSeriesValues(DisplayStatus.NOT_MAPPED)
    if not isinstance(timeseries, Mapping):
        return TimeSeriesValues(DisplayStatus.INVALID)
    series = timeseries.get('series')
    if not isinstance(series, Mapping):
        return TimeSeriesValues(DisplayStatus.INVALID)
    if key not in series:
        return TimeSeriesValues(DisplayStatus.NOT_MAPPED)
    try:
        entry = series[key]
        if not isinstance(entry, Mapping):
            raise ValueError('Time series entry must be an object')
        hours = entry['hours']
        step = timeseries['step_seconds']
        if type(hours) is not int or not 1 <= hours <= 24:
            raise ValueError('Time series hours must be between 1 and 24')
        if type(step) is not int or step != _STEP_SECONDS:
            raise ValueError('Time series step is unsupported')
        start, end, delivery_end = (
            _utc(entry['start_utc']),
            _utc(entry['end_utc']),
            _utc(timeseries['end_utc']),
        )
        if end != delivery_end or start != end - timedelta(hours=hours):
            raise ValueError('Time series bounds are inconsistent')
        samples = entry['values']
        if not isinstance(samples, list) or len(samples) != hours * 3600 // step:
            raise ValueError('Time series samples count is inconsistent')
        value_type = entry['value_type']
        if value_type not in {'integer', 'float', None}:
            raise ValueError('Colectiva trend must be numeric')
        if value_type is None and any(sample is not None for sample in samples):
            raise ValueError('Time series values require numeric type')
        points = tuple(
            TimeSeriesPoint(start + timedelta(seconds=step * (index + 1)), sample)
            for index, sample in enumerate(samples)
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return TimeSeriesValues(DisplayStatus.INVALID)
    return TimeSeriesValues(DisplayStatus.OK, points)


# Acepta timestamps con zona horaria y normaliza a UTC.
def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError('Time series timestamp must be an ISO string')
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('Time series timestamp must be timezone-aware')
    return stamp.astimezone(UTC)
