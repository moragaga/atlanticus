# Expone la API contractual pública de Materialization y el resolver puro B.2.
# El resolver no adquiere datos ni persiste artifacts: sólo transforma inputs ya cargados.
from ada_command_center.alarms.materialization.delivery import (
    DeliveryAlarmConfiguration,
    ResolvedDeactivationPolicy,
    ResolvedDeliveryAlarm,
    ResolvedDeliveryMessage,
    ResolvedVisualSubcomponentTarget,
    ResolvedVisualTarget,
)
from ada_command_center.alarms.materialization.qualification import (
    EvaluatorQualificationCatalog,
    EvaluatorQualificationKey,
    ToolReconciliationQualification,
)
from ada_command_center.alarms.materialization.resolution import (
    AlarmConfigurationResolution,
    AlarmResolutionFinding,
    AlarmResolutionFindingSeverity,
    AlarmResolutionStatus,
)
from ada_command_center.alarms.materialization.resolver import resolve_alarm_configuration
from ada_command_center.alarms.materialization.runtime import RuntimeAlarmConfiguration

__version__ = '1.0.0'

__all__ = [
    'AlarmConfigurationResolution',
    'AlarmResolutionFinding',
    'AlarmResolutionFindingSeverity',
    'AlarmResolutionStatus',
    'DeliveryAlarmConfiguration',
    'EvaluatorQualificationCatalog',
    'EvaluatorQualificationKey',
    'ToolReconciliationQualification',
    'ResolvedDeactivationPolicy',
    'ResolvedDeliveryAlarm',
    'ResolvedDeliveryMessage',
    'ResolvedVisualSubcomponentTarget',
    'ResolvedVisualTarget',
    'RuntimeAlarmConfiguration',
    '__version__',
    'resolve_alarm_configuration',
]
