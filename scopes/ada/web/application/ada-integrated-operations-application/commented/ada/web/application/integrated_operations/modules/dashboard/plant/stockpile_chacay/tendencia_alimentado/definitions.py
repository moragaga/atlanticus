from __future__ import annotations

# Claves provisionales recuperadas de ada-old-legacy:main; no constituyen autoridad de KPI.
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AlimentadoTrendDefinition:
    key: str
    label: str
    kpi_key: str


ALIMENTADO_TRENDS = (
    AlimentadoTrendDefinition('axb', 'AXB Alimentado', 'axb_alimentado_hora'),
    AlimentadoTrendDefinition(
        'recuperacion_cu', 'Recuperación Cu Alimentado', 'recuperacion_cu_alimentado_hora'
    ),
    AlimentadoTrendDefinition('ley_cu', 'Ley Cu Alimentado', 'ley_cu_alimentado_hora'),
)
