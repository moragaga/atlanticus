# Definiciones de claves tomadas de los legacy y agrupadas por responsabilidad.
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MoliendaMetricDefinition:
    label: str
    kpi_key: str
    unit: str | None = None
    color_kpi_key: str | None = None


MOLIENDA_TREND = MoliendaMetricDefinition('Rendimiento Molienda', 'rendimiento_real_mean_hora')

MOLIENDA_GENERAL_METRICS = (
    MoliendaMetricDefinition('Avance Pebbles', 'avance_pebbles_real'),
    MoliendaMetricDefinition('Recirculación', 'recirculacion_pebbles_mean_hora'),
    MoliendaMetricDefinition('CEE Planta', 'cee_planta_mean_hora'),
    MoliendaMetricDefinition('P80 Planta', 'p80_planta_real'),
)
