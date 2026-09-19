from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    StorageResourceContract,
    StorageResourceOverrideField,
)

PROFILES_PROJECTION_STORAGE_RESOURCE: StorageResourceContract[CosmosContainerTopology] = (
    StorageResourceContract(
        logical_id='profiles.projection',
        owner='profiles',
        provider='cosmos',
        default_connection_ref=None,
        default_physical_name='profiles-projection',
        topology=CosmosContainerTopology(
            partition_key_path='/partition_key',
            default_ttl_seconds=None,
        ),
        allowed_overrides=frozenset({StorageResourceOverrideField.CONNECTION_REF}),
    )
)

PROFILES_PROJECTION_STORAGE_RESOURCES: tuple[
    StorageResourceContract[CosmosContainerTopology], ...
] = (PROFILES_PROJECTION_STORAGE_RESOURCE,)
