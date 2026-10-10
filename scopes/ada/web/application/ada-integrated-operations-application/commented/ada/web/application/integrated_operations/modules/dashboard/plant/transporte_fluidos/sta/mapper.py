from ada.web.kpis.readings import (
    read_component_latest,
)

from ..indicators import FluidMetricReading, map_metrics
from .definitions import STA_INDICATORS


# La card reutiliza el contrato común y aplica exclusivamente sus definiciones.
def map_sta_store(store_data: object) -> tuple[FluidMetricReading, ...]:
    return map_metrics(read_component_latest(store_data), STA_INDICATORS)
