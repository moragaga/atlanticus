from __future__ import annotations

from collections.abc import Mapping

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.kpis.readings import read_component_latest
from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .colectiva.overview.definitions import COLECTIVA_INDICATORS, COLECTIVA_TREND
from .colectiva.process.definitions import (
    BOMBAS,
    COLUMNS_OPERATING_KEY,
    COLUMNS_TOTAL_KEY,
    ROUGHERS,
    SCAVENGERS,
    VERTIMILLS,
)
from .selectiva.espesadores.definitions import ESPESADORES
from .selectiva.indicators.definitions import SELECTIVA_INDICATORS

_KEYS = tuple(
    dict.fromkeys(
        (
            COLECTIVA_TREND.kpi_key,
            *(item.kpi_key for item in COLECTIVA_INDICATORS),
            *(item.state_kpi_key for item in ROUGHERS),
            *(item.state_kpi_key for item in SCAVENGERS),
            *(
                key
                for item in VERTIMILLS
                for key in (item.state_kpi_key, item.amperage_kpi_key)
            ),
            *(item.state_kpi_key for group in BOMBAS for item in group),
            COLUMNS_OPERATING_KEY,
            COLUMNS_TOTAL_KEY,
            *(
                key
                for item in ESPESADORES
                for key in (
                    item.state_kpi_key,
                    item.feed_kpi_key,
                    *(metric.kpi_key for metric in item.metrics),
                )
            ),
            *(item.kpi_key for item in SELECTIVA_INDICATORS),
        )
    )
)
_KEYS = tuple(key for key in _KEYS if key is not None)


# Decodifica las claves de ambas tarjetas una sola vez. Timeseries se entrega sin transformar.
def decode_flotacion_store(store_data: object) -> tuple[dict[str, DisplayValue], object]:
    latest = read_component_latest(store_data)
    readings = {key: _read(latest, key) for key in _KEYS}
    timeseries = (
        store_data.get('timeseries')
        if isinstance(store_data, Mapping)
        else DisplayStatus.INVALID
    )
    return readings, timeseries


# Conserva el estado individual de cada KPI y muestra parsed_value como texto.
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
