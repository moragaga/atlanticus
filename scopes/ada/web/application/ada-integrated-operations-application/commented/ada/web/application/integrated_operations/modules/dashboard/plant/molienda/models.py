# Agrupa las lecturas de tendencia, filas, SAG y molinos sin alterar sus estados.
from __future__ import annotations

from dataclasses import dataclass

from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)
from ada.web.ui.display_status import DisplayValue
from ada.web.ui.time_series import TimeSeriesValues

from .definitions import (
    MoliendaEquipmentDefinition,
    MoliendaLineDefinition,
    MoliendaMetricDefinition,
)


@dataclass(frozen=True, slots=True)
class MoliendaMetricReading:
    definition: MoliendaMetricDefinition
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
    metrics: tuple[MoliendaMetricReading, ...]


@dataclass(frozen=True, slots=True)
class MoliendaState:
    trend_current: DisplayValue
    trend_history: TimeSeriesValues
    general: tuple[MoliendaMetricReading, ...]
    lines: tuple[MoliendaLineReading, ...]
