from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from ada.web.ui.display_status import (
    DisplayStatus,
    DisplayValue,
    ValueSeverity,
    map_value_severity_code,
)
from ada.web.ui.time_series import TimeSeriesPoint, TimeSeriesValues

from .definitions import MOLIENDA_GENERAL_METRICS, MOLIENDA_TREND, MoliendaMetricDefinition
from .models import MoliendaMetricReading, MoliendaOverviewReading

_STEP_SECONDS = 120


def map_molienda_overview_readings(
    readings: Mapping[str, DisplayValue], timeseries: object
) -> MoliendaOverviewReading:
    return MoliendaOverviewReading(
        trend_current=readings[MOLIENDA_TREND.kpi_key],
        trend_history=_history(timeseries, MOLIENDA_TREND.kpi_key),
        general=tuple(_metric(readings, definition) for definition in MOLIENDA_GENERAL_METRICS),
    )


def _tone(readings: Mapping[str, DisplayValue], key: str | None) -> ValueSeverity:
    if key is None:
        return ValueSeverity.NEUTRAL
    reading = readings[key]
    if reading.status is not DisplayStatus.OK:
        return ValueSeverity.NEUTRAL
    try:
        return map_value_severity_code(reading.value)
    except ValueError:
        return ValueSeverity.NEUTRAL


def _metric(
    readings: Mapping[str, DisplayValue], definition: MoliendaMetricDefinition
) -> MoliendaMetricReading:
    return MoliendaMetricReading(
        definition=definition,
        value=readings[definition.kpi_key],
        tone=_tone(readings, definition.color_kpi_key),
    )


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError('Time series timestamp must be a non-empty ISO string')
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
            raise ValueError('Time series hours must be between 1 and 24')
        step = timeseries['step_seconds']
        if type(step) is not int or step != _STEP_SECONDS:
            raise ValueError('Time series step_seconds is unsupported')
        start = _utc(entry['start_utc'])
        end = _utc(entry['end_utc'])
        if end != _utc(timeseries['end_utc']) or start != end - timedelta(hours=hours):
            raise ValueError('Time series bounds are inconsistent')
        samples = entry['values']
        if not isinstance(samples, list) or len(samples) != hours * 3600 // step:
            raise ValueError('Time series samples count is inconsistent')
        value_type = entry['value_type']
        if value_type not in {'integer', 'float', None}:
            raise ValueError('Molienda trend must be numeric')
        if value_type is None and any(value is not None for value in samples):
            raise ValueError('Time series values require numeric value_type')
        points = tuple(
            TimeSeriesPoint(start + timedelta(seconds=step * (index + 1)), sample)
            for index, sample in enumerate(samples)
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return TimeSeriesValues(DisplayStatus.INVALID)
    return TimeSeriesValues(DisplayStatus.OK, points)
