from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.level_gauge import LevelGaugeView
from ada.web.ui.time_series import TimeSeriesValues

from .definitions import FilterDefinition


@dataclass(frozen=True, slots=True)
class FilterReading:
    definition: FilterDefinition
    state: DisplayValue


@dataclass(frozen=True, slots=True)
class PuertoReading:
    trend_current: DisplayValue
    trend_history: TimeSeriesValues
    accumulated: DisplayValue
    tanks: tuple[LevelGaugeView, ...]
    filters: tuple[FilterReading, ...]
    tonnage: DisplayValue
    duration: DisplayValue
    duration_unit: str
    ship_state: DisplayValue
