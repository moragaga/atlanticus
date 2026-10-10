from ..metrics import FluidMetricReading, map_metrics
from .definitions import TRANQUE_INDICATORS


# Explicación: este bloque implementa la misma responsabilidad que su par productivo.
def map_tranque_store(store_data: object) -> tuple[FluidMetricReading, ...]:
    return map_metrics(store_data, TRANQUE_INDICATORS)
