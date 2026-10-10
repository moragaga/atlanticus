from __future__ import annotations

from dataclasses import dataclass


# Claves y orden de KPI recuperados desde las referencias legacy indicadas.
@dataclass(frozen=True, slots=True)
class MetricDefinition:
    label: str
    kpi_key: str
    unit: str | None = None
