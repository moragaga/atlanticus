# Para presentación se consume parsed_value; los datos de cálculo usan value neutral.
from __future__ import annotations

from collections.abc import Mapping

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.stockpile import StockpileValues

from .definitions import STOCKPILE_MINA_KPI_KEYS


def map_stockpile_mina_store(store_data: object) -> tuple[StockpileValues, ...]:
    values, source_status = _latest_values(store_data)
    return tuple(
        StockpileValues(
            percent=_map_reading(values, percentage_key, source_status),
            height_m=_map_reading(values, height_m_key, source_status),
        )
        for _, percentage_key, height_m_key in STOCKPILE_MINA_KPI_KEYS
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


def _map_reading(
    values: Mapping[str, object] | None,
    kpi_key: str,
    source_status: DisplayStatus,
) -> DisplayValue:
    if values is None:
        return DisplayValue(source_status)
    decoded = decode_kpi_latest_value(values.get(kpi_key), present=kpi_key in values)
    if decoded.state is KpiLatestValueState.OK:
        if decoded.value_kind != 'value' or not isinstance(decoded.parsed_value, str):
            return DisplayValue.invalid()
        return DisplayValue.ok(decoded.parsed_value)
    if decoded.state is KpiLatestValueState.NOT_MAPPED:
        return DisplayValue.not_mapped()
    if decoded.state is KpiLatestValueState.MISSING:
        return DisplayValue.empty()
    if decoded.state is KpiLatestValueState.ERROR:
        return DisplayValue.error()
    return DisplayValue.invalid()
