from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FluidMetricDefinition:
    label: str
    kpi_key: str
    unit: str
