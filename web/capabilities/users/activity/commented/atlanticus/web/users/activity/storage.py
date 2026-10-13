# Contrato de contenedor Cosmos propio para sesiones de actividad temporales.
# El TTL fijo se renueva con cada escritura por el timestamp _ts de Cosmos.
# No usar TTL individual ni mezclar con recursos durables de Users.
# La aplicación consumidora resuelve explícitamente la conexión nombrada.
from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    StorageResourceContract,
    StorageResourceOverrideField,
)
from atlanticus.web.users.activity.models import USER_ACTIVITY_PARTITION_KEY_PATH

USER_ACTIVITY_STORAGE_RESOURCE: StorageResourceContract[CosmosContainerTopology] = (
    StorageResourceContract(
        logical_id='users.activity',
        owner='users',
        provider='cosmos',
        default_connection_ref=None,
        default_physical_name='users-activity',
        topology=CosmosContainerTopology(
            partition_key_path=USER_ACTIVITY_PARTITION_KEY_PATH,
            default_ttl_seconds=86_400,
        ),
        allowed_overrides=frozenset({StorageResourceOverrideField.CONNECTION_REF}),
    )
)

USER_ACTIVITY_STORAGE_RESOURCES: tuple[
    StorageResourceContract[CosmosContainerTopology], ...
] = (USER_ACTIVITY_STORAGE_RESOURCE,)
