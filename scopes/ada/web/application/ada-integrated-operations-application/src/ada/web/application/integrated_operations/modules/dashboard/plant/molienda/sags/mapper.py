from __future__ import annotations

from collections.abc import Mapping

from ada.web.ui.display_status import (
    DisplayStatus,
    DisplayValue,
    ValueSeverity,
    map_value_severity_code,
)

from .definitions import (
    MOLIENDA_LINES,
    MoliendaEquipmentDefinition,
    MoliendaLineDefinition,
    MoliendaSagMetricDefinition,
)
from .models import MoliendaEquipmentReading, MoliendaLineReading, MoliendaSagMetricReading


def map_molienda_sags_readings(
    readings: Mapping[str, DisplayValue],
) -> tuple[MoliendaLineReading, ...]:
    return tuple(_line(readings, definition) for definition in MOLIENDA_LINES)


def _tone(readings: Mapping[str, DisplayValue], key: str | None) -> ValueSeverity:
    if key is None:
        return ValueSeverity.NEUTRAL
    reading = readings[key]
    if reading.status is not DisplayStatus.OK:
        return ValueSeverity.NEUTRAL
    try:
        return map_value_severity_code(reading.value)
    except ValueError:
        return ValueSeverity.NEUTRAL


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
