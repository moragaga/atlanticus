from __future__ import annotations

from collections.abc import Mapping

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .definitions import SELECTIVA_INDICATORS
from .models import SelectivaIndicatorReading


def map_selectiva_indicators_store(store_data: object) -> tuple[SelectivaIndicatorReading, ...]:
    values, status = _latest_values(store_data)
    return tuple(
        SelectivaIndicatorReading(definition, _value(values, definition.kpi_key, status))
        for definition in SELECTIVA_INDICATORS
    )


def _latest_values(store_data: object) -> tuple[Mapping[str, object] | None, DisplayStatus]:
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
