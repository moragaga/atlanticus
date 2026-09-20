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
