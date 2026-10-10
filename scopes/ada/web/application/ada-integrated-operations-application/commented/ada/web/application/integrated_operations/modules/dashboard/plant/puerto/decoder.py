from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.kpis.readings import read_component_latest
from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.time_series import TimeSeriesPoint, TimeSeriesValues

from .desaladora.definitions import FLUJO_TREND, VOLUMEN
from .puerto.definitions import FILTERS, FILTRADO_ACCUMULATED, FILTRADO_TREND, SHIPMENT, TANKS

_STEP_SECONDS = 120
_TREND_KEYS = (FILTRADO_TREND.kpi_key, FLUJO_TREND.kpi_key)
_LEVEL_KEYS = frozenset(tank.level_key for tank in TANKS)
_KEYS = tuple(
    dict.fromkeys(
        (
            FILTRADO_TREND.kpi_key,
            FILTRADO_ACCUMULATED.kpi_key,
            *(key for tank in TANKS for key in (tank.level_key, tank.color_key)),
            *(item.state_key for item in FILTERS),
            SHIPMENT.tonnage.kpi_key,
            SHIPMENT.duration_key,
            SHIPMENT.state_key,
            FLUJO_TREND.kpi_key,
            VOLUMEN.kpi_key,
        )
    )
)


# Lectura única del Store KPI y validación independiente de las series de Puerto y Desaladora.
def decode_puerto_store(
    store_data: object,
) -> tuple[dict[str, DisplayValue], dict[str, TimeSeriesValues]]:
    source = read_component_latest(store_data)
    readings = {
        key: source.scalar(key) if key in _LEVEL_KEYS else _text(source, key) for key in _KEYS
    }
    timeseries = (
        store_data.get('timeseries') if isinstance(store_data, Mapping) else []
    )
    histories = {key: _history(timeseries, key) for key in _TREND_KEYS}
    return readings, histories


def _text(source, key: str) -> DisplayValue:
    if source.values is None:
        return DisplayValue(source.source_status)
    decoded = decode_kpi_latest_value(source.values.get(key), present=key in source.values)
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
    return DisplayValue.ok(str(decoded.parsed_value))


def _history(timeseries: object, key: str) -> TimeSeriesValues:
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
        start = _utc(entry['start_utc'])
        end = _utc(entry['end_utc'])
        if end != _utc(timeseries['end_utc']) or start != end - timedelta(hours=hours):
            raise ValueError('Time series bounds are inconsistent')
        values = entry['values']
        if not isinstance(values, list) or len(values) != hours * 3600 // step:
            raise ValueError('Time series samples count is inconsistent')
        value_type = entry['value_type']
        if value_type not in {'integer', 'float', None}:
            raise ValueError('Time series values must be numeric')
        if value_type is None and any(value is not None for value in values):
            raise ValueError('Time series values require numeric type')
        points = tuple(
            TimeSeriesPoint(start + timedelta(seconds=step * (index + 1)), value)
            for index, value in enumerate(values)
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return TimeSeriesValues(DisplayStatus.INVALID)
    return TimeSeriesValues(DisplayStatus.OK, points)


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError('Time series timestamp must be an ISO string')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Time series timestamp must be timezone-aware')
    return parsed.astimezone(UTC)
