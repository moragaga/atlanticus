from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    StorageResourceContract,
    StorageResourceOverrideField,
)

KPI_REGISTRY_PROJECTION_STORAGE_RESOURCE: StorageResourceContract[CosmosContainerTopology] = (
    StorageResourceContract(
        logical_id='ada.kpis.registry.projection',
        owner='ada.kpis.registry',
        provider='cosmos',
        default_connection_ref=None,
        default_physical_name='ada-kpi-registry-projection',
        topology=CosmosContainerTopology(
            partition_key_path='/partition_key',
            default_ttl_seconds=None,
        ),
        allowed_overrides=frozenset({StorageResourceOverrideField.CONNECTION_REF}),
    )
)

KPI_REGISTRY_PROJECTION_STORAGE_RESOURCES: tuple[
    StorageResourceContract[CosmosContainerTopology], ...
] = (KPI_REGISTRY_PROJECTION_STORAGE_RESOURCE,)
