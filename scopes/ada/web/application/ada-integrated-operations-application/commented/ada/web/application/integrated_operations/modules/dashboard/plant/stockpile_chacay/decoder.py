# Se decodifica Latest una sola vez por KPI; Timeseries se entrega sin transformar al mapper del dominio.
from __future__ import annotations

from collections.abc import Mapping

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.kpis.readings import read_component_latest
from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .feeders.definitions import STOCKPILE_CHACAY_FEEDER_GROUPS, ChacayFeederDefinition
from .stockpile.definitions import (
    STOCKPILE_CHACAY_PILES,
    STOCKPILE_CHACAY_POSITION_KEY,
    STOCKPILE_CHACAY_ROWS,
)
from .tendencia_alimentado.definitions import ALIMENTADO_TRENDS

_STOCKPILE_KEYS = (
    STOCKPILE_CHACAY_POSITION_KEY,
    *(item.kpi_key for item in STOCKPILE_CHACAY_PILES),
    *(item.kpi_key for item in STOCKPILE_CHACAY_ROWS),
)
_TREND_KEYS = tuple(item.kpi_key for item in ALIMENTADO_TRENDS)


def decode_stockpile_chacay_store(
    store_data: object,
    *,
    feeder_definitions: tuple[tuple[ChacayFeederDefinition, ...], ...] = (
        STOCKPILE_CHACAY_FEEDER_GROUPS
    ),
) -> tuple[dict[str, DisplayValue], object]:
    latest = read_component_latest(store_data)
    feeder_keys = tuple(
        key
        for group in feeder_definitions
        for item in group
        for key in (item.value_kpi_key, item.color_kpi_key)
        if key is not None
    )
    keys = dict.fromkeys((*_STOCKPILE_KEYS, *feeder_keys, *_TREND_KEYS))
    result = {}
    for key in keys:
        if latest.values is None:
            status = latest.source_status
            if key in _TREND_KEYS and not isinstance(store_data, Mapping):
                status = DisplayStatus.NOT_MAPPED
            result[key] = DisplayValue(status)
            continue
        decoded = decode_kpi_latest_value(latest.values.get(key), present=key in latest.values)
        if decoded.state is KpiLatestValueState.NOT_MAPPED:
            result[key] = DisplayValue.not_mapped()
        elif decoded.state is KpiLatestValueState.MISSING:
            result[key] = DisplayValue.empty()
        elif decoded.state is KpiLatestValueState.ERROR:
            result[key] = DisplayValue.error()
        elif decoded.state is not KpiLatestValueState.OK:
            result[key] = DisplayValue.invalid()
        elif key in feeder_keys:
            value = decoded.value
            result[key] = (
                DisplayValue.ok(value)
                if decoded.value_kind == 'value'
                and not isinstance(value, bool)
                and isinstance(value, str | int | float)
                else DisplayValue.invalid()
            )
        else:
            value = decoded.parsed_value
            if (
                (key in _TREND_KEYS and decoded.value_kind != 'value')
                or isinstance(value, bool)
                or not isinstance(value, str | int | float)
            ):
                result[key] = DisplayValue.invalid()
            else:
                stripped = str(value).strip()
                result[key] = DisplayValue.ok(stripped) if stripped else DisplayValue.invalid()
    timeseries = store_data.get('timeseries') if isinstance(store_data, Mapping) else None
    return result, timeseries
