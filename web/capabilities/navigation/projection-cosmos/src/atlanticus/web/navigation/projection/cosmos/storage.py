from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    StorageResourceContract,
    StorageResourceOverrideField,
)

NAVIGATION_PROJECTION_STORAGE_RESOURCE: StorageResourceContract[CosmosContainerTopology] = (
    StorageResourceContract(
        logical_id='navigation.projection',
        owner='navigation',
        provider='cosmos',
        default_connection_ref=None,
        default_physical_name='navigation-projection',
        topology=CosmosContainerTopology(
            partition_key_path='/partition_key',
            default_ttl_seconds=None,
        ),
        allowed_overrides=frozenset({StorageResourceOverrideField.CONNECTION_REF}),
    )
)

NAVIGATION_PROJECTION_STORAGE_RESOURCES: tuple[
    StorageResourceContract[CosmosContainerTopology], ...
] = (NAVIGATION_PROJECTION_STORAGE_RESOURCE,)
