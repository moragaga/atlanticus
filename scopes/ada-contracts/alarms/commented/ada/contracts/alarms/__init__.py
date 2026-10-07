# Esta superficie pública expone únicamente contratos de Alarmas que pueden cruzar productos.
# La lógica se mantiene equivalente al archivo productivo; sólo se agregan comentarios pedagógicos.

from ada.contracts.alarms.configuration import AlarmConfiguration
from ada.contracts.alarms.definition import (
    DEACTIVATION_MAX_HOURS,
    END_OF_SHIFT,
    AlarmColor,
    AlarmDeactivationDefinition,
    AlarmDefinition,
    AlarmEscalationDefinition,
    AlarmEscalationStepDefinition,
    AlarmVisualSubcomponentTarget,
    AlarmVisualTarget,
    BusinessCategory,
    DeactivationLimit,
    MessageDeactivationDefinition,
    MessageDefinition,
    MessageScope,
    OperationalArea,
    ProcessAlarmProjectionMode,
    ReappearanceDefinition,
    VisibilityMode,
)
from ada.contracts.alarms.errors import (
    AlarmConfigurationProjectionValidationError,
    AlarmConfigurationValidationError,
)
from ada.contracts.alarms.models import AlarmIdentity, AlarmKind, Criticality
from ada.contracts.alarms.projection import (
    ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE,
    ALARM_CONFIGURATION_PROJECTION_SCHEMA_VERSION,
    ALARM_CONFIGURATION_SOURCE_KEY,
    AlarmConfigurationProjection,
    AlarmConfigurationProjectionDependency,
)
from ada.contracts.alarms.snapshot import AlarmConfigurationSnapshot

__version__ = '1.0.0'

__all__ = [
    'ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE',
    'ALARM_CONFIGURATION_PROJECTION_SCHEMA_VERSION',
    'ALARM_CONFIGURATION_SOURCE_KEY',
    'DEACTIVATION_MAX_HOURS',
    'END_OF_SHIFT',
    'AlarmColor',
    'AlarmConfiguration',
    'AlarmConfigurationProjection',
    'AlarmConfigurationProjectionDependency',
    'AlarmConfigurationProjectionValidationError',
    'AlarmConfigurationSnapshot',
    'AlarmConfigurationValidationError',
    'AlarmDeactivationDefinition',
    'AlarmDefinition',
    'AlarmEscalationDefinition',
    'AlarmEscalationStepDefinition',
    'AlarmIdentity',
    'AlarmKind',
    'AlarmVisualSubcomponentTarget',
    'AlarmVisualTarget',
    'BusinessCategory',
    'Criticality',
    'DeactivationLimit',
    'MessageDeactivationDefinition',
    'MessageDefinition',
    'MessageScope',
    'OperationalArea',
    'ProcessAlarmProjectionMode',
    'ReappearanceDefinition',
    'VisibilityMode',
    '__version__',
]
