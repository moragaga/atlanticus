# Lecturas inmutables para mantener los valores y estados independientes.
from __future__ import annotations

from dataclasses import dataclass

from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)
from ada.web.ui.display_status import DisplayValue

from .definitions import (
    MoliendaEquipmentDefinition,
    MoliendaLineDefinition,
    MoliendaSagMetricDefinition,
)


@dataclass(frozen=True, slots=True)
class MoliendaSagMetricReading:
    definition: MoliendaSagMetricDefinition
    value: DisplayValue
    tone: DashboardValueStatus = DashboardValueStatus.NEUTRAL


@dataclass(frozen=True, slots=True)
class MoliendaEquipmentReading:
    definition: MoliendaEquipmentDefinition
    state: DisplayValue
    power: DisplayValue
    power_tone: DashboardValueStatus = DashboardValueStatus.NEUTRAL


@dataclass(frozen=True, slots=True)
class MoliendaLineReading:
    definition: MoliendaLineDefinition
    sag: MoliendaEquipmentReading
    mills: tuple[MoliendaEquipmentReading, ...]
    metrics: tuple[MoliendaSagMetricReading, ...]
