# Contrato interno del contenedor Timeseries.
# Espejo pedagógico; los comentarios no alteran el AST productivo.
from atlanticus.connectivity.cosmos import CosmosContainerSpec

KPI_TIMESERIES_DELIVERY_CONTAINER_SPEC = CosmosContainerSpec(
    name='ada-kpi-timeseries-delivery',
    partition_key_path='/partition_id',
    default_ttl_seconds=None,
)
