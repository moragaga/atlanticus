from ..metrics import FluidMetricReading, map_metrics
from .definitions import STA_INDICATORS


# Explicación: este bloque implementa la misma responsabilidad que su par productivo.
def map_sta_store(store_data: object) -> tuple[FluidMetricReading, ...]:
    return map_metrics(store_data, STA_INDICATORS)
