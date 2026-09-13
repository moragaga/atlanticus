from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    StorageResourceContract,
    StorageResourceOverrideField,
)

# Users posee un único recurso durable para pending y managed; ambos estados comparten identidad y ciclo de vida.
USERS_RUNTIME_STORAGE_RESOURCE: StorageResourceContract[CosmosContainerTopology] = (
    StorageResourceContract(
        logical_id='users.runtime',
        owner='users',
        provider='cosmos',
        # La composición debe seleccionar explícitamente qué conexión Cosmos satisface este recurso.
        default_connection_ref=None,
        default_physical_name='users-runtime',
        topology=CosmosContainerTopology(
            # user_id identifica y particiona cada identidad de forma independiente.
            partition_key_path='/id',
            # Users es durable: Cosmos no debe eliminar automáticamente estos documentos.
            default_ttl_seconds=None,
        ),
        # V1 permite variar únicamente la conexión; la forma y el nombre físico permanecen contractuales.
        allowed_overrides=frozenset({StorageResourceOverrideField.CONNECTION_REF}),
    )
)

# La tupla ofrece una superficie estable de registro sin acoplar Users al resolver ni al provider físico.
USERS_STORAGE_RESOURCES: tuple[StorageResourceContract[CosmosContainerTopology], ...] = (
    USERS_RUNTIME_STORAGE_RESOURCE,
)
