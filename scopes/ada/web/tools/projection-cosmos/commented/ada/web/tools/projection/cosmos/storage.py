# Declara el container físico compartido por todas las Tool Projections.
# La separación por aplicación/Tool ocurre dentro del store mediante partition_key.

from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    StorageResourceContract,
    StorageResourceOverrideField,
)

TOOL_PROJECTION_STORAGE_RESOURCE: StorageResourceContract[
    CosmosContainerTopology
] = StorageResourceContract(
    logical_id='ada.tools.projection',
    owner='ada.tools',
    provider='cosmos',
    default_connection_ref=None,
    default_physical_name='ada-tool-projection',
    topology=CosmosContainerTopology(
        partition_key_path='/partition_key',
        default_ttl_seconds=None,
    ),
    allowed_overrides=frozenset(
        {StorageResourceOverrideField.CONNECTION_REF}
    ),
)

TOOL_PROJECTION_STORAGE_RESOURCES: tuple[
    StorageResourceContract[CosmosContainerTopology],
    ...,
] = (TOOL_PROJECTION_STORAGE_RESOURCE,)
