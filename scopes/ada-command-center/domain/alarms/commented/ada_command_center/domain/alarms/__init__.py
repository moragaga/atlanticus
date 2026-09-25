# API pública única del dominio transversal de alarmas.
from ada_command_center.domain.alarms.configuration import AlarmConfiguration
from ada_command_center.domain.alarms.definition import (
    AlarmColor,
    AlarmDeactivationDefinition,
    AlarmDefinition,
    AlarmEscalationDefinition,
    AlarmEscalationStepDefinition,
    AlarmVisualSubcomponentTarget,
    AlarmVisualTarget,
    BusinessCategory,
    MessageDeactivationDefinition,
    MessageDefinition,
    MessageScope,
    OperationalArea,
    ProcessAlarmProjectionMode,
    ReappearanceDefinition,
    VisibilityMode,
)
from ada_command_center.domain.alarms.errors import AlarmConfigurationValidationError
from ada_command_center.domain.alarms.models import AlarmIdentity, AlarmKind, Criticality
from ada_command_center.domain.alarms.snapshot import AlarmConfigurationSnapshot

__version__ = '1.0.0'

__all__ = [
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
    'MessageDeactivationDefinition',
    'MessageDefinition',
    'MessageScope',
    'OperationalArea',
    'ProcessAlarmProjectionMode',
    'ReappearanceDefinition',
    'VisibilityMode',
    '__version__',
]
