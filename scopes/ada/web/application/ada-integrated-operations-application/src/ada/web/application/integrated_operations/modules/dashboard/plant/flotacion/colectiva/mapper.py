from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.time_series import TimeSeriesPoint, TimeSeriesValues

_STEP_SECONDS = 120


def latest_values(store_data: object) -> tuple[Mapping[str, object] | None, DisplayStatus]:
    if not isinstance(store_data, Mapping):
        return None, DisplayStatus.INVALID
    latest = store_data.get('latest')
    if latest is None:
        return None, DisplayStatus.NOT_MAPPED
    if not isinstance(latest, Mapping):
        return None, DisplayStatus.INVALID
    values = latest.get('values')
    if not isinstance(values, Mapping):
        return None, DisplayStatus.INVALID
    return values, DisplayStatus.OK


def display_value(
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
    if decoded.value_kind != 'value' or isinstance(decoded.value, bool):
        return DisplayValue.invalid()
    if not isinstance(decoded.value, str | int | float):
        return DisplayValue.invalid()
    raw = str(decoded.value).strip()
    return DisplayValue.ok(raw) if raw else DisplayValue.invalid()


def history_values(store_data: object, key: str) -> TimeSeriesValues:
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


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError('Time series timestamp must be an ISO string')
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('Time series timestamp must be timezone-aware')
    return stamp.astimezone(UTC)
