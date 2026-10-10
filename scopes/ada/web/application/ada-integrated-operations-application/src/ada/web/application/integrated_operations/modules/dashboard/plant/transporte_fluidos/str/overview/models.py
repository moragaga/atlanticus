from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.time_series import TimeSeriesValues


@dataclass(frozen=True, slots=True)
class StrOverviewReading:
    current: DisplayValue
    history: TimeSeriesValues
