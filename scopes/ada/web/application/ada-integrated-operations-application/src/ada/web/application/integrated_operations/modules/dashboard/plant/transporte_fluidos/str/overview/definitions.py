from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StrTrendDefinition:
    label: str
    kpi_key: str
    unit: str


STR_TREND = StrTrendDefinition('Relave', 'relave_real_mean_hora', 't/h')
