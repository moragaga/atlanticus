from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
# Punto de responsabilidad: SelectivaIndicatorDefinition; mantiene el mismo contrato que producción.
class SelectivaIndicatorDefinition:
    label: str
    kpi_key: str
    unit: str


# Nombres, orden, unidades y claves obtenidos de la configuración del old legacy.
SELECTIVA_INDICATORS = (
    SelectivaIndicatorDefinition('Conc Colectivo', 'concentrado_colectivo_real_mean_hora', 't/h'),
    SelectivaIndicatorDefinition('Ley Mo Env', 'ley_concentrado_mo_real', '%'),
    SelectivaIndicatorDefinition('Utilización', 'utilizacion_flotacion_selectiva', '%'),
    SelectivaIndicatorDefinition('Recuperación', 'recuperacion_selectiva_mo', '%'),
    SelectivaIndicatorDefinition('NaHS', 'nash_real', 'kg/t'),
    SelectivaIndicatorDefinition('Producción', 'produccion_selectiva_mo', 'tmf'),
)
