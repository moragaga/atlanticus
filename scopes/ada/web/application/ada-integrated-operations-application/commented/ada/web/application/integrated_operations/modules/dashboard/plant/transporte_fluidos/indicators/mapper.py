from __future__ import annotations

from collections.abc import Sequence

from ada.web.kpis.readings import (
    KpiLatestReadings,
)

from .definitions import FluidMetricDefinition
from .models import FluidMetricReading


# Cada KPI se lee desde el contrato compartido; los estados degradados permanecen independientes.
def map_metrics(
    source: KpiLatestReadings, definitions: Sequence[FluidMetricDefinition]
) -> tuple[FluidMetricReading, ...]:
    return tuple(FluidMetricReading(item, source.text(item.kpi_key)) for item in definitions)
