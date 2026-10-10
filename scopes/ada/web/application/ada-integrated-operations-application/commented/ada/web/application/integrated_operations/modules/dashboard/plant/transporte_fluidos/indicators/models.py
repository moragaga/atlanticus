from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue

from .definitions import FluidMetricDefinition


@dataclass(frozen=True, slots=True)
# El resultado combina la definición estable con el valor ya validado y su estado.
class FluidMetricReading:
    definition: FluidMetricDefinition
    value: DisplayValue
