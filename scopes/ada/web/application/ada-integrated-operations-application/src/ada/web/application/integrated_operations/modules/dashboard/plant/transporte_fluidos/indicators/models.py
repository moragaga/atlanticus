from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue

from .definitions import FluidMetricDefinition


@dataclass(frozen=True, slots=True)
class FluidMetricReading:
    definition: FluidMetricDefinition
    value: DisplayValue
