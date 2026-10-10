from __future__ import annotations

from collections.abc import Mapping

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .definitions import (
    BOMBAS,
    COLUMNS_OPERATING_KEY,
    COLUMNS_TOTAL_KEY,
    ROUGHERS,
    SCAVENGERS,
    VERTIMILLS,
    ColectivaEquipmentDefinition,
    ColectivaStateDefinition,
)
from .models import ColectivaEquipmentReading, ColectivaProcessReading, ColectivaStateReading


def map_colectiva_process_store(store_data: object) -> ColectivaProcessReading:
    values, status = _latest_values(store_data)

    def state(definition: ColectivaStateDefinition) -> ColectivaStateReading:
        return ColectivaStateReading(
            definition=definition,
            state=_display_value(values, definition.state_kpi_key, status),
        )

    def equipment(definition: ColectivaEquipmentDefinition) -> ColectivaEquipmentReading:
        return ColectivaEquipmentReading(
            definition=definition,
            state=_display_value(values, definition.state_kpi_key, status),
            amperage=(
                _display_value(values, definition.amperage_kpi_key, status)
                if definition.amperage_kpi_key is not None
                else None
            ),
        )

    return ColectivaProcessReading(
        roughers=tuple(map(state, ROUGHERS)),
        vertimills=tuple(map(equipment, VERTIMILLS)),
        bombas=tuple(tuple(map(equipment, group)) for group in BOMBAS),
        columns_operating=_display_value(values, COLUMNS_OPERATING_KEY, status),
        columns_total=_display_value(values, COLUMNS_TOTAL_KEY, status),
        scavengers=tuple(map(state, SCAVENGERS)),
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


def _display_value(
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
