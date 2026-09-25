# Espejo pedagógico en español; el comportamiento equivale al archivo de src.
# Solo se reexportan contratos y implementaciones propias; los stores se seleccionan desde composition.
from ada_command_center.web.alarms.projection.cosmos.storage import (
    ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE,
    ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCES,
)
from ada_command_center.web.alarms.projection.cosmos.store import (
    CosmosAlarmConfigurationProjectionStore,
    CosmosAlarmConfigurationProjectionStoreSettings,
)

__all__ = [
    'ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE',
    'ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCES',
    'CosmosAlarmConfigurationProjectionStore',
    'CosmosAlarmConfigurationProjectionStoreSettings',
]
