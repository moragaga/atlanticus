from __future__ import annotations

from collections.abc import Mapping

from ada.web.ui.display_status import DisplayValue

from ..indicators import FluidMetricReading, map_metrics
from .definitions import TRANQUE_INDICATORS


def map_tranque_readings(readings: Mapping[str, DisplayValue]) -> tuple[FluidMetricReading, ...]:
    return map_metrics(readings, TRANQUE_INDICATORS)
