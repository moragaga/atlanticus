from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import (
    DisplayValue,
    ValueSeverity,
)

from .definitions import (
    MoliendaEquipmentDefinition,
    MoliendaLineDefinition,
    MoliendaSagMetricDefinition,
)


@dataclass(frozen=True, slots=True)
class MoliendaSagMetricReading:
    definition: MoliendaSagMetricDefinition
    value: DisplayValue
    tone: ValueSeverity = ValueSeverity.NEUTRAL


@dataclass(frozen=True, slots=True)
class MoliendaEquipmentReading:
    definition: MoliendaEquipmentDefinition
    state: DisplayValue
    power: DisplayValue
    power_tone: ValueSeverity = ValueSeverity.NEUTRAL


@dataclass(frozen=True, slots=True)
class MoliendaLineReading:
    definition: MoliendaLineDefinition
    sag: MoliendaEquipmentReading
    mills: tuple[MoliendaEquipmentReading, ...]
    metrics: tuple[MoliendaSagMetricReading, ...]
