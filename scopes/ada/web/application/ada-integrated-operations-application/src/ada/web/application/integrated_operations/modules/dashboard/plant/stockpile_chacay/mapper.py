from __future__ import annotations

from collections.abc import Mapping

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.stockpile import StockpileValues

from .definitions import (
    STOCKPILE_CHACAY_PILES,
    STOCKPILE_CHACAY_POSITION_KEY,
    STOCKPILE_CHACAY_POSITIONS,
    STOCKPILE_CHACAY_ROWS,
)
from .feeders import map_chacay_feeders_store
from .models import ChacayMetric, StockpileChacayState


def map_stockpile_chacay_store(store_data: object) -> StockpileChacayState:
    values, source_status = _latest_values(store_data)
    position = _reading(values, STOCKPILE_CHACAY_POSITION_KEY, source_status)
    if position.status is DisplayStatus.OK:
        number = str(position.value).strip()
        if number not in {str(value) for value in STOCKPILE_CHACAY_POSITIONS}:
            position = DisplayValue.invalid()
        else:
            position = DisplayValue.ok(int(number))
    return StockpileChacayState(
        position=position,
        piles=tuple(
            StockpileValues(percent=_reading(values, definition.kpi_key, source_status))
            for definition in STOCKPILE_CHACAY_PILES
        ),
        feeders=map_chacay_feeders_store(store_data),
        rows=tuple(
            ChacayMetric(
                key=definition.key,
                label=definition.label,
                kpi_key=definition.kpi_key,
                value=_reading(values, definition.kpi_key, source_status),
            )
            for definition in STOCKPILE_CHACAY_ROWS
        ),
    )


def _latest_values(
    store_data: object,
) -> tuple[Mapping[str, object] | None, DisplayStatus]:
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


def _reading(
    values: Mapping[str, object] | None,
    kpi_key: str,
    source_status: DisplayStatus,
) -> DisplayValue:
    if values is None:
        return DisplayValue(source_status)
    decoded = decode_kpi_latest_value(values.get(kpi_key), present=kpi_key in values)
    if decoded.state is KpiLatestValueState.NOT_MAPPED:
        return DisplayValue.not_mapped()
    if decoded.state is KpiLatestValueState.MISSING:
        return DisplayValue.empty()
    if decoded.state is KpiLatestValueState.ERROR:
        return DisplayValue.error()
    if decoded.state is not KpiLatestValueState.OK:
        return DisplayValue.invalid()
    if isinstance(decoded.value, bool) or not isinstance(decoded.value, str | int | float):
        return DisplayValue.invalid()
    raw = str(decoded.value).strip()
    return DisplayValue.ok(raw) if raw else DisplayValue.invalid()
