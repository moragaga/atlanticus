from __future__ import annotations

from dataclasses import dataclass

from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)
from ada.web.ui.display_status import DisplayValue
from ada.web.ui.time_series import TimeSeriesValues

from .definitions import MoliendaMetricDefinition


@dataclass(frozen=True, slots=True)
class MoliendaMetricReading:
    definition: MoliendaMetricDefinition
    value: DisplayValue
    tone: DashboardValueStatus = DashboardValueStatus.NEUTRAL


@dataclass(frozen=True, slots=True)
class MoliendaOverviewReading:
    trend_current: DisplayValue
    trend_history: TimeSeriesValues
    general: tuple[MoliendaMetricReading, ...]
