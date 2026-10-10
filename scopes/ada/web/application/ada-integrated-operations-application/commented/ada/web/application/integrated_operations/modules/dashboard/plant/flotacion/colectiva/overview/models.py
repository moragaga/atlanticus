# Agrupa lecturas inmutables con sus definiciones para la presentación.
from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.time_series import TimeSeriesValues

from .definitions import ColectivaIndicatorDefinition


@dataclass(frozen=True, slots=True)
class ColectivaIndicatorReading:
    definition: ColectivaIndicatorDefinition
    value: DisplayValue


@dataclass(frozen=True, slots=True)
class ColectivaOverviewReading:
    trend_current: DisplayValue
    trend_history: TimeSeriesValues
    indicators: tuple[ColectivaIndicatorReading, ...]
