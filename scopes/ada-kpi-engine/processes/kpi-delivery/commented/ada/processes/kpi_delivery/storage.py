# Espejo pedagógico del módulo productivo.
# Los comentarios explican la responsabilidad de la frontera sin alterar su semántica.
# Contratos físicos de los contenedores consumido y poseído por Latest Delivery.
# El Registry sólo se valida; el output Latest sí puede asegurarse al arranque.
from atlanticus.connectivity.cosmos import CosmosContainerSpec

KPI_REGISTRY_CONTAINER_SPEC = CosmosContainerSpec(
    name='ada-kpi-registry-projection',
    partition_key_path='/partition_key',
    default_ttl_seconds=None,
)
KPI_LATEST_DELIVERY_CONTAINER_SPEC = CosmosContainerSpec(
    name='ada-kpi-latest-delivery',
    partition_key_path='/partition_id',
    default_ttl_seconds=None,
)
KPI_REGISTRY_PARTITION_VALUE = 'kpis'
