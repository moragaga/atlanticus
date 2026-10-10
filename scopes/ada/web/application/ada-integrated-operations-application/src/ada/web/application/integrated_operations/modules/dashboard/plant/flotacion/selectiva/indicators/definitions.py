from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SelectivaIndicatorDefinition:
    label: str
    kpi_key: str
    unit: str


SELECTIVA_INDICATORS = (
    SelectivaIndicatorDefinition('Conc Colectivo', 'concentrado_colectivo_real_mean_hora', 't/h'),
    SelectivaIndicatorDefinition('Ley Mo Env', 'ley_concentrado_mo_real', '%'),
    SelectivaIndicatorDefinition('Utilización', 'utilizacion_flotacion_selectiva', '%'),
    SelectivaIndicatorDefinition('Recuperación', 'recuperacion_selectiva_mo', '%'),
    SelectivaIndicatorDefinition('NaHS', 'nash_real', 'kg/t'),
    SelectivaIndicatorDefinition('Producción', 'produccion_selectiva_mo', 'tmf'),
)
