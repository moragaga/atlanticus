# Definiciones de claves tomadas de los legacy y agrupadas por responsabilidad.
# Las unidades de las cuatro métricas generales se declaran aquí, no en CSS ni en el mapper.
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
    MoliendaMetricDefinition('Avance Pebbles', 'avance_pebbles_real', 't/h'),
    MoliendaMetricDefinition('Recirculación Pebbles', 'recirculacion_pebbles_mean_hora', 't/h'),
    MoliendaMetricDefinition('CEE Planta', 'cee_planta_mean_hora', 'kW/t'),
    MoliendaMetricDefinition('P80 Planta', 'p80_planta_real', 'µm'),
)
