from ada_command_center.web.alarms.configuration.resources import (
    ALARM_CONFIGURATION_PROJECTION_PHYSICAL_NAME,
)
from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    StorageResourceContract,
    StorageResourceOverrideField,
)

ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE: StorageResourceContract[
    CosmosContainerTopology
] = StorageResourceContract(
    logical_id='ada.command_center.alarms.configuration.projection',
    owner='ada.command_center.alarms.configuration',
    provider='cosmos',
    default_connection_ref=None,
    default_physical_name=ALARM_CONFIGURATION_PROJECTION_PHYSICAL_NAME,
    topology=CosmosContainerTopology(
        partition_key_path='/partition_key',
        default_ttl_seconds=None,
    ),
    allowed_overrides=frozenset({StorageResourceOverrideField.CONNECTION_REF}),
)

ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCES: tuple[
    StorageResourceContract[CosmosContainerTopology], ...
] = (ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE,)
