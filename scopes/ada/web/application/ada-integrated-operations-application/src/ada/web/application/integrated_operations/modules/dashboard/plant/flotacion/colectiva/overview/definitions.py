from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ColectivaIndicatorDefinition:
    label: str
    kpi_key: str
    unit: str | None = None


COLECTIVA_TREND = ColectivaIndicatorDefinition('Recuperación Cu', 'recuperacion_cu_lab')
COLECTIVA_INDICATORS = (
    ColectivaIndicatorDefinition('Ley Cu', 'ley_cu_lab'),
    ColectivaIndicatorDefinition('Malla 325', 'malla_325_lab'),
    ColectivaIndicatorDefinition('Malla 100', 'malla_100_lab'),
    ColectivaIndicatorDefinition('Ley Concentrado', 'ley_concentrado_lab'),
    ColectivaIndicatorDefinition('Ley Colas', 'ley_colas_lab'),
)
