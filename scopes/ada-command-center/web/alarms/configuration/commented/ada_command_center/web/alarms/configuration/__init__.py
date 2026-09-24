# Espejo pedagógico en español; el comportamiento equivale al archivo de src.
# Solo se reexportan contratos y implementaciones propias; los stores se seleccionan desde composition.
from ada_command_center.web.alarms.configuration.errors import (
    AlarmConfigurationProjectionError,
    AlarmConfigurationSourceError,
)
from ada_command_center.web.alarms.configuration.projection_record import (
    ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE,
    ALARM_CONFIGURATION_PROJECTION_SCHEMA_VERSION,
    alarm_configuration_projection_from_document,
    alarm_configuration_projection_to_document,
)
from ada_command_center.web.alarms.configuration.source_projection import (
    AlarmConfigurationProjectionBuilder,
    create_alarm_configuration_projection_service,
)
from ada_command_center.web.alarms.configuration.source_release import (
    ALARM_CONFIGURATION_SOURCE_DOCUMENT_TYPE,
    ALARM_CONFIGURATION_SOURCE_RESOURCE_PATH,
    ALARM_CONFIGURATION_SOURCE_SCHEMA_VERSION,
    AlarmConfigurationSourceCodec,
    AlarmConfigurationSourcePayload,
    AlarmConfigurationSourceRelease,
    AlarmConfigurationSourceService,
)
from ada_command_center.web.alarms.configuration.tool_references import (
    AlarmToolComponentReference,
    AlarmToolReference,
    AlarmToolReferenceCatalog,
    AlarmToolReferenceReader,
    AlarmToolSubcomponentReference,
)

__version__ = '0.1.0'

__all__ = [
    'ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE',
    'ALARM_CONFIGURATION_PROJECTION_SCHEMA_VERSION',
    'ALARM_CONFIGURATION_SOURCE_DOCUMENT_TYPE',
    'ALARM_CONFIGURATION_SOURCE_RESOURCE_PATH',
    'ALARM_CONFIGURATION_SOURCE_SCHEMA_VERSION',
    'AlarmConfigurationProjectionBuilder',
    'AlarmConfigurationProjectionError',
    'AlarmConfigurationSourceCodec',
    'AlarmConfigurationSourceError',
    'AlarmConfigurationSourcePayload',
    'AlarmConfigurationSourceRelease',
    'AlarmConfigurationSourceService',
    'AlarmToolComponentReference',
    'AlarmToolReference',
    'AlarmToolReferenceCatalog',
    'AlarmToolReferenceReader',
    'AlarmToolSubcomponentReference',
    'alarm_configuration_projection_from_document',
    'alarm_configuration_projection_to_document',
    'create_alarm_configuration_projection_service',
    '__version__',
]
