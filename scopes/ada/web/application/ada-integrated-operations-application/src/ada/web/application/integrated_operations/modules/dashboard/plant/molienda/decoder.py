from __future__ import annotations

from collections.abc import Mapping

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.kpis.readings import read_component_latest
from ada.web.ui.display_status import DisplayValue

from .overview.definitions import MOLIENDA_GENERAL_METRICS, MOLIENDA_TREND
from .sags.definitions import MOLIENDA_LINES

_KEYS = tuple(
    dict.fromkeys(
        (
            MOLIENDA_TREND.kpi_key,
            MOLIENDA_TREND.color_kpi_key,
            *(
                key
                for metric in MOLIENDA_GENERAL_METRICS
                for key in (metric.kpi_key, metric.color_kpi_key)
            ),
            *(
                key
                for line in MOLIENDA_LINES
                for equipment in (line.sag, *line.mills)
                for key in (
                    equipment.state_kpi_key,
                    equipment.power_kpi_key,
                    equipment.power_color_kpi_key,
                )
            ),
            *(
                key
                for line in MOLIENDA_LINES
                for metric in line.metrics
                for key in (metric.kpi_key, metric.color_kpi_key)
            ),
        )
    )
)
_KEYS = tuple(key for key in _KEYS if key is not None)


def decode_molienda_store(store_data: object) -> tuple[dict[str, DisplayValue], object]:
    latest = read_component_latest(store_data)
    readings = {key: _read(latest, key) for key in _KEYS}
    timeseries = store_data.get('timeseries') if isinstance(store_data, Mapping) else None
    return readings, timeseries


def _read(latest, key: str) -> DisplayValue:
    if latest.values is None:
        return DisplayValue(latest.source_status)
    decoded = decode_kpi_latest_value(latest.values.get(key), present=key in latest.values)
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
    value = str(decoded.parsed_value).strip()
    return DisplayValue.ok(value) if value else DisplayValue.invalid()
