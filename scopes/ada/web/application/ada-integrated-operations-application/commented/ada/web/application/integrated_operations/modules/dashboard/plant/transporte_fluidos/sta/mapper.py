# Versión pedagógica: Los indicadores de STA ya no decodifican un Store por separado.
from __future__ import annotations

from collections.abc import Mapping

from ada.web.ui.display_status import DisplayValue

from ..indicators import FluidMetricReading, map_metrics
from .definitions import STA_INDICATORS


def map_sta_readings(readings: Mapping[str, DisplayValue]) -> tuple[FluidMetricReading, ...]:
    return map_metrics(readings, STA_INDICATORS)
