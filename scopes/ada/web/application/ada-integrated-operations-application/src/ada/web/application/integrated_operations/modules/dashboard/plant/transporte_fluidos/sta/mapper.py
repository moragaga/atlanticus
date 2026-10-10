from ..metrics import FluidMetricReading, map_metrics
from .definitions import STA_INDICATORS


def map_sta_store(store_data: object) -> tuple[FluidMetricReading, ...]:
    return map_metrics(store_data, STA_INDICATORS)
