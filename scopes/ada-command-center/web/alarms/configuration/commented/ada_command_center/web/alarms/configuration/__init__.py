# Este módulo expone la API pública del paquete de configuración de alarmas.
# Mantiene separados el contrato editable/persistible y el motor operacional.
# Source/Release se publica desde esta frontera Web y el backend core permanece sin cambios.
from ada_command_center.web.alarms.configuration.errors import (
    AlarmConfigurationSourceError,
    AlarmConfigurationValidationError,
)
from ada_command_center.web.alarms.configuration.models import AlarmConfiguration
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

__version__ = '0.1.0'

__all__ = [
    'ALARM_CONFIGURATION_SOURCE_DOCUMENT_TYPE',
    'ALARM_CONFIGURATION_SOURCE_RESOURCE_PATH',
    'ALARM_CONFIGURATION_SOURCE_SCHEMA_VERSION',
    'AlarmConfiguration',
    'AlarmConfigurationProjectionBuilder',
    'AlarmConfigurationSourceCodec',
    'AlarmConfigurationSourceError',
    'AlarmConfigurationSourcePayload',
    'AlarmConfigurationSourceRelease',
    'AlarmConfigurationSourceService',
    'AlarmConfigurationValidationError',
    'create_alarm_configuration_projection_service',
    '__version__',
]
