# Espejo pedagógico en español; el comportamiento equivale al archivo de src.
from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    StorageResourceContract,
    StorageResourceOverrideField,
)

# Recurso declarativo Cosmos. Database y cliente se resuelven por fuera; no se acopla el dominio a infraestructura.
ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE: StorageResourceContract[
    CosmosContainerTopology
] = StorageResourceContract(
    logical_id='ada.command_center.alarms.configuration.projection',
    owner='ada.command_center.alarms.configuration',
    provider='cosmos',
    default_connection_ref=None,
    default_physical_name='ada-command-center-alarm-configuration-projection',
    topology=CosmosContainerTopology(
        partition_key_path='/partition_key',
        default_ttl_seconds=None,
    ),
    allowed_overrides=frozenset({StorageResourceOverrideField.CONNECTION_REF}),
)

ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCES: tuple[
    StorageResourceContract[CosmosContainerTopology], ...
] = (ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE,)
