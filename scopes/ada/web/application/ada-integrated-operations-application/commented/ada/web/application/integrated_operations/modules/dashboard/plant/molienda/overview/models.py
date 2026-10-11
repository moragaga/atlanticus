# Lecturas inmutables para mantener los valores y estados independientes.
from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import (
    DisplayValue,
    ValueSeverity,
)
from ada.web.ui.time_series import TimeSeriesValues

from .definitions import MoliendaMetricDefinition


@dataclass(frozen=True, slots=True)
class MoliendaMetricReading:
    definition: MoliendaMetricDefinition
    value: DisplayValue
    tone: ValueSeverity = ValueSeverity.NEUTRAL


@dataclass(frozen=True, slots=True)
class MoliendaOverviewReading:
    trend_current: DisplayValue
    trend_history: TimeSeriesValues
    general: tuple[MoliendaMetricReading, ...]
