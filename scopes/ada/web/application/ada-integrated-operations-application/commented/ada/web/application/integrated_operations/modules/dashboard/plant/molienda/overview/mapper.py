# Para presentación se consume parsed_value; los datos de cálculo usan value neutral.
from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
    map_dashboard_value_status,
)
from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.time_series import TimeSeriesPoint, TimeSeriesValues

from .definitions import MOLIENDA_GENERAL_METRICS, MOLIENDA_TREND, MoliendaMetricDefinition
from .models import MoliendaMetricReading, MoliendaOverviewReading

_STEP_SECONDS = 120


def map_molienda_overview_store(store_data: object) -> MoliendaOverviewReading:
    data = store_data if isinstance(store_data, Mapping) else None
    values, source_status = _latest_values(data)
    timeseries = data.get('timeseries') if data is not None else None
    return MoliendaOverviewReading(
        trend_current=_value(values, MOLIENDA_TREND.kpi_key, source_status),
        trend_history=_history(timeseries, MOLIENDA_TREND.kpi_key),
        general=tuple(
            _metric(values, definition, source_status) for definition in MOLIENDA_GENERAL_METRICS
        ),
    )


def _latest_values(
    data: Mapping[str, object] | None,
) -> tuple[Mapping[str, object] | None, DisplayStatus]:
    if data is None:
        return None, DisplayStatus.INVALID
    latest = data.get('latest')
    if latest is None:
        return None, DisplayStatus.NOT_MAPPED
    if not isinstance(latest, Mapping):
        return None, DisplayStatus.INVALID
    values = latest.get('values')
    if not isinstance(values, Mapping):
        return None, DisplayStatus.INVALID
    return values, DisplayStatus.OK


def _value(
    values: Mapping[str, object] | None,
    key: str,
    source_status: DisplayStatus,
) -> DisplayValue:
    if values is None:
        return DisplayValue(source_status)
    decoded = decode_kpi_latest_value(values.get(key), present=key in values)
    if decoded.state is KpiLatestValueState.NOT_MAPPED:
        return DisplayValue.not_mapped()
    if decoded.state is KpiLatestValueState.MISSING:
        return DisplayValue.empty()
    if decoded.state is KpiLatestValueState.ERROR:
        return DisplayValue.error()
    if decoded.state is not KpiLatestValueState.OK:
        return DisplayValue.invalid()
    if decoded.value_kind != 'value' or isinstance(decoded.parsed_value, bool):
        return DisplayValue.invalid()
    if not isinstance(decoded.parsed_value, str | int | float):
        return DisplayValue.invalid()
    raw = str(decoded.parsed_value).strip()
    return DisplayValue.ok(raw) if raw else DisplayValue.invalid()


def _tone(
    values: Mapping[str, object] | None,
    key: str | None,
    source_status: DisplayStatus,
) -> DashboardValueStatus:
    if key is None:
        return DashboardValueStatus.NEUTRAL
    reading = _value(values, key, source_status)
    if reading.status is not DisplayStatus.OK:
        return DashboardValueStatus.NEUTRAL
    try:
        return map_dashboard_value_status(reading.value)
    except ValueError:
        return DashboardValueStatus.NEUTRAL


def _metric(
    values: Mapping[str, object] | None,
    definition: MoliendaMetricDefinition,
    source_status: DisplayStatus,
) -> MoliendaMetricReading:
    return MoliendaMetricReading(
        definition=definition,
        value=_value(values, definition.kpi_key, source_status),
        tone=_tone(values, definition.color_kpi_key, source_status),
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
    except KeyError, TypeError, ValueError, OverflowError:
        return TimeSeriesValues(DisplayStatus.INVALID)
    return TimeSeriesValues(DisplayStatus.OK, points)
