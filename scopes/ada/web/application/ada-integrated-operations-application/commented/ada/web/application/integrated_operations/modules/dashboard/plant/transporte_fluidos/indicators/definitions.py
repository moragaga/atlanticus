from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
# La definición conserva etiqueta, clave y unidad sin consultar datos ni construir UI.
class FluidMetricDefinition:
    label: str
    kpi_key: str
    unit: str
