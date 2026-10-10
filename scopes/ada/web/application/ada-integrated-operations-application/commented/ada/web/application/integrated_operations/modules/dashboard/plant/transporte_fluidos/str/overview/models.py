from __future__ import annotations

# Versión pedagógica: conserva literalmente la lógica y contratos del módulo productivo.


from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.time_series import TimeSeriesValues


@dataclass(frozen=True, slots=True)
class StrOverviewReading:
    current: DisplayValue
    history: TimeSeriesValues
