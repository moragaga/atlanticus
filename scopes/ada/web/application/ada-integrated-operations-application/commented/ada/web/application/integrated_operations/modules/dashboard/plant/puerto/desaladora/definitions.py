# Claves y orden de KPI recuperados desde las referencias legacy indicadas.
from __future__ import annotations

from dataclasses import dataclass


# Definición independiente de los dos KPI de Desaladora.
@dataclass(frozen=True, slots=True)
class MetricDefinition:
    label: str
    kpi_key: str
    unit: str | None = None


FLUJO_TREND = MetricDefinition('Flujo Desaladora', 'flujo_real_mean_hora')
# El cambio de etiqueta y unidad es visual: la clave y los datos permanecen intactos.
VOLUMEN = MetricDefinition('Impulsión Día', 'volumen_real_acc_dia', 'l/s')
