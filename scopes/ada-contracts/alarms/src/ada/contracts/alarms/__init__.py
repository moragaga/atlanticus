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
from ada.contracts.alarms.errors import AlarmConfigurationValidationError
from ada.contracts.alarms.models import AlarmIdentity, AlarmKind, Criticality
from ada.contracts.alarms.snapshot import AlarmConfigurationSnapshot

__version__ = '1.0.0'

__all__ = [
    'DEACTIVATION_MAX_HOURS',
    'END_OF_SHIFT',
    'AlarmColor',
    'AlarmConfiguration',
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
