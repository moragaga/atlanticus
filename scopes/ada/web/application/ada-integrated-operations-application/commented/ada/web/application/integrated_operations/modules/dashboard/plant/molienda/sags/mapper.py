from __future__ import annotations

from collections.abc import Mapping

from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
    map_dashboard_value_status,
)
from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .definitions import (
    MOLIENDA_LINES,
    MoliendaEquipmentDefinition,
    MoliendaLineDefinition,
    MoliendaSagMetricDefinition,
)
from .models import MoliendaEquipmentReading, MoliendaLineReading, MoliendaSagMetricReading


# Los cuatro SAG y sus molinos comparten los valores preparados, conservando el orden de sus definiciones.
def map_molienda_sags_readings(
    readings: Mapping[str, DisplayValue],
) -> tuple[MoliendaLineReading, ...]:
    return tuple(_line(readings, definition) for definition in MOLIENDA_LINES)


# El estado del color es independiente del estado de la lectura mostrada.
def _tone(readings: Mapping[str, DisplayValue], key: str | None) -> DashboardValueStatus:
    if key is None:
        return DashboardValueStatus.NEUTRAL
    reading = readings[key]
    if reading.status is not DisplayStatus.OK:
        return DashboardValueStatus.NEUTRAL
    try:
        return map_dashboard_value_status(reading.value)
    except ValueError:
        return DashboardValueStatus.NEUTRAL


def _metric(
    readings: Mapping[str, DisplayValue], definition: MoliendaSagMetricDefinition
) -> MoliendaSagMetricReading:
    return MoliendaSagMetricReading(
        definition=definition,
        value=readings[definition.kpi_key],
        tone=_tone(readings, definition.color_kpi_key),
    )


def _equipment(
    readings: Mapping[str, DisplayValue], definition: MoliendaEquipmentDefinition
) -> MoliendaEquipmentReading:
    return MoliendaEquipmentReading(
        definition=definition,
        state=readings[definition.state_kpi_key],
        power=readings[definition.power_kpi_key],
        power_tone=_tone(readings, definition.power_color_kpi_key),
    )


def _line(
    readings: Mapping[str, DisplayValue], definition: MoliendaLineDefinition
) -> MoliendaLineReading:
    return MoliendaLineReading(
        definition=definition,
        sag=_equipment(readings, definition.sag),
        mills=tuple(_equipment(readings, mill) for mill in definition.mills),
        metrics=tuple(_metric(readings, metric) for metric in definition.metrics),
    )
