from __future__ import annotations

from collections.abc import Mapping

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.time_series import TimeSeriesValues

from .definitions import FLUJO_TREND, VOLUMEN
from .models import DesaladoraReading


def map_desaladora_readings(
    readings: Mapping[str, DisplayValue], histories: Mapping[str, TimeSeriesValues]
) -> DesaladoraReading:
    return DesaladoraReading(
        trend_current=readings[FLUJO_TREND.kpi_key],
        trend_history=histories[FLUJO_TREND.kpi_key],
        volume=readings[VOLUMEN.kpi_key],
    )
