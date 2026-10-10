from __future__ import annotations

from collections.abc import Mapping

from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
    map_dashboard_value_status,
)
from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .definitions import (
    MOLIENDA_LINES,
    MoliendaEquipmentDefinition,
    MoliendaLineDefinition,
    MoliendaSagMetricDefinition,
)
from .models import MoliendaEquipmentReading, MoliendaLineReading, MoliendaSagMetricReading


def map_molienda_sags_store(store_data: object) -> tuple[MoliendaLineReading, ...]:
    data = store_data if isinstance(store_data, Mapping) else None
    values, source_status = _latest_values(data)
    return tuple(_line(values, definition, source_status) for definition in MOLIENDA_LINES)


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
    if decoded.value_kind != 'value' or isinstance(decoded.value, bool):
        return DisplayValue.invalid()
    if not isinstance(decoded.value, str | int | float):
        return DisplayValue.invalid()
    raw = str(decoded.value).strip()
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
    definition: MoliendaSagMetricDefinition,
    source_status: DisplayStatus,
) -> MoliendaSagMetricReading:
    return MoliendaSagMetricReading(
        definition=definition,
        value=_value(values, definition.kpi_key, source_status),
        tone=_tone(values, definition.color_kpi_key, source_status),
    )


def _equipment(
    values: Mapping[str, object] | None,
    definition: MoliendaEquipmentDefinition,
    source_status: DisplayStatus,
) -> MoliendaEquipmentReading:
    return MoliendaEquipmentReading(
        definition=definition,
        state=_value(values, definition.state_kpi_key, source_status),
        power=_value(values, definition.power_kpi_key, source_status),
        power_tone=_tone(values, definition.power_color_kpi_key, source_status),
    )


def _line(
    values: Mapping[str, object] | None,
    definition: MoliendaLineDefinition,
    source_status: DisplayStatus,
) -> MoliendaLineReading:
    return MoliendaLineReading(
        definition=definition,
        sag=_equipment(values, definition.sag, source_status),
        mills=tuple(_equipment(values, mill, source_status) for mill in definition.mills),
        metrics=tuple(_metric(values, metric, source_status) for metric in definition.metrics),
    )
