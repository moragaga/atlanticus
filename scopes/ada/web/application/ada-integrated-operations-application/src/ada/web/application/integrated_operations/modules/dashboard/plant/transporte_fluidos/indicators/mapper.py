from __future__ import annotations

from collections.abc import Mapping, Sequence

from ada.web.ui.display_status import DisplayValue

from .definitions import FluidMetricDefinition
from .models import FluidMetricReading


def map_metrics(
    readings: Mapping[str, DisplayValue], definitions: Sequence[FluidMetricDefinition]
) -> tuple[FluidMetricReading, ...]:
    return tuple(FluidMetricReading(item, readings[item.kpi_key]) for item in definitions)
