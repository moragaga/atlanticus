from atlanticus.connectivity.cosmos import CosmosContainerSpec

KPI_LATEST_DELIVERY_CONTAINER_SPEC = CosmosContainerSpec(
    name='ada-kpi-latest-delivery',
    partition_key_path='/partition_id',
    default_ttl_seconds=None,
)
