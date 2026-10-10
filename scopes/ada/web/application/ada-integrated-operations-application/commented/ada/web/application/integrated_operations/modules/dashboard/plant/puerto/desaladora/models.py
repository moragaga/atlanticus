from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.time_series import TimeSeriesValues


# Contratos inmutables utilizados entre mapper y presentación.
@dataclass(frozen=True, slots=True)
class DesaladoraReading:
    trend_current: DisplayValue
    trend_history: TimeSeriesValues
    volume: DisplayValue
