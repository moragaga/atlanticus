# Espejo pedagógico del módulo productivo.
# Los comentarios explican la responsabilidad de la frontera sin alterar su semántica.
# Contratos físicos del Registry consumido y del output Timeseries poseído por este proceso.
# El input nunca se crea desde aquí; el output propio se asegura al arranque.
from atlanticus.connectivity.cosmos import CosmosContainerSpec

KPI_REGISTRY_CONTAINER_SPEC = CosmosContainerSpec(
    name='ada-kpi-registry-projection',
    partition_key_path='/partition_key',
    default_ttl_seconds=None,
)
KPI_TIMESERIES_DELIVERY_CONTAINER_SPEC = CosmosContainerSpec(
    name='ada-kpi-timeseries-delivery',
    partition_key_path='/partition_id',
    default_ttl_seconds=None,
)
KPI_REGISTRY_PARTITION_VALUE = 'kpis'
