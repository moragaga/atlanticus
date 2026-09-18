# Espejo pedagógico: este contrato declara exclusivamente el recurso Cosmos usado para resolución runtime.
# El registro durable Blob pertenece al provider de registry y no se disfraza como otro recurso Cosmos.
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
