"""
Superficie pública de Materialization para ADA Alarm Engine.

Reúne los contratos Engine, Modeler y Delivery, sus codecs y el resolvedor puro.
"""
from ada.alarms.materialization.codec import (
    delivery_from_document,
    delivery_to_document,
    engine_from_document,
    engine_to_document,
    modeler_from_document,
    modeler_to_document,
)
from ada.alarms.materialization.delivery import DeliveryAlarmConfiguration
from ada.alarms.materialization.engine import EngineAlarmConfiguration
from ada.alarms.materialization.modeler import (
    ModelerAlarmConfiguration,
    ResolvedDeactivationPolicy,
    ResolvedModelerAlarm,
    ResolvedModelerMessage,
    ResolvedVisualSubcomponentTarget,
    ResolvedVisualTarget,
)
from ada.alarms.materialization.qualification import (
    EvaluatorQualificationCatalog,
    EvaluatorQualificationKey,
    ToolReconciliationQualification,
)
from ada.alarms.materialization.resolution import (
    AlarmConfigurationResolution,
    AlarmResolutionFinding,
    AlarmResolutionFindingSeverity,
    AlarmResolutionStatus,
)
from ada.alarms.materialization.resolver import resolve_alarm_configuration
from ada.alarms.materialization.routing_policy import next_routing_tool_kind

__version__ = '1.0.0'

__all__ = [
    'AlarmConfigurationResolution',
    'AlarmResolutionFinding',
    'AlarmResolutionFindingSeverity',
    'AlarmResolutionStatus',
    'DeliveryAlarmConfiguration',
    'EngineAlarmConfiguration',
    'EvaluatorQualificationCatalog',
    'EvaluatorQualificationKey',
    'ModelerAlarmConfiguration',
    'ResolvedDeactivationPolicy',
    'ResolvedModelerAlarm',
    'ResolvedModelerMessage',
    'ResolvedVisualSubcomponentTarget',
    'ResolvedVisualTarget',
    'ToolReconciliationQualification',
    '__version__',
    'delivery_from_document',
    'delivery_to_document',
    'engine_from_document',
    'engine_to_document',
    'modeler_from_document',
    'modeler_to_document',
    'next_routing_tool_kind',
    'resolve_alarm_configuration',
]
