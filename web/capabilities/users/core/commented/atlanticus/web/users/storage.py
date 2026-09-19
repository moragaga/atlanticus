# Los recursos físicos de Users se declaran aquí sin transferir ownership de los documentos que alojan.
# Runtime conserva su contenedor propio y Support agrupa documentos auxiliares con contratos independientes.
from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    StorageResourceContract,
    StorageResourceOverrideField,
)

USERS_RUNTIME_STORAGE_RESOURCE: StorageResourceContract[CosmosContainerTopology] = (
    StorageResourceContract(
        logical_id='users.runtime',
        owner='users',
        provider='cosmos',
        default_connection_ref=None,
        default_physical_name='users-runtime',
        topology=CosmosContainerTopology(
            partition_key_path='/id',
            default_ttl_seconds=None,
        ),
        allowed_overrides=frozenset({StorageResourceOverrideField.CONNECTION_REF}),
    )
)

USERS_RUNTIME_STORAGE_RESOURCES: tuple[
    StorageResourceContract[CosmosContainerTopology], ...
] = (USERS_RUNTIME_STORAGE_RESOURCE,)

# Support es solo un contenedor físico compartido; cada capability mantiene su serializer y document_type.
USERS_SUPPORT_STORAGE_RESOURCE: StorageResourceContract[CosmosContainerTopology] = (
    StorageResourceContract(
        logical_id='users.support',
        owner='users',
        provider='cosmos',
        default_connection_ref=None,
        default_physical_name='users-support',
        topology=CosmosContainerTopology(
            partition_key_path='/partition_key',
            default_ttl_seconds=None,
        ),
        allowed_overrides=frozenset({StorageResourceOverrideField.CONNECTION_REF}),
    )
)

USERS_SUPPORT_STORAGE_RESOURCES: tuple[
    StorageResourceContract[CosmosContainerTopology], ...
] = (USERS_SUPPORT_STORAGE_RESOURCE,)
