# Codec contractual compartido entre escritor y lectores Runtime/Delivery.
# No serializa ejecutables ni consulta el Tool Catalog actual.
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum

from ada.web.tools.enums import ToolConfigurationKind
from ada_command_center.alarms.core import (
    AlarmResolutionKey,
    AlarmRouting,
    DeactivationPolicy,
    PlannedAlarm,
    RoutingDestination,
)
from ada_command_center.alarms.materialization.delivery import (
    DeliveryAlarmConfiguration,
    ResolvedDeactivationPolicy,
    ResolvedDeliveryAlarm,
    ResolvedDeliveryMessage,
    ResolvedVisualSubcomponentTarget,
    ResolvedVisualTarget,
)
from ada_command_center.alarms.materialization.runtime import RuntimeAlarmConfiguration
from ada_command_center.domain.alarms import (
    AlarmColor,
    AlarmIdentity,
    AlarmKind,
    BusinessCategory,
    Criticality,
    OperationalArea,
    ProcessAlarmProjectionMode,
    VisibilityMode,
)


def _json_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _json_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError('Alarm materialization JSON mapping keys must be strings')
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, str | float | int | bool):
        return value
    raise TypeError('Alarm materialization JSON contains an unsupported value')


def _identity(identity: AlarmIdentity) -> dict[str, object]:
    return {'family_key': identity.family_key, 'alarm_key': identity.alarm_key}


def _decode_identity(document: dict[str, object]) -> AlarmIdentity:
    return AlarmIdentity(family_key=document['family_key'], alarm_key=document['alarm_key'])


def _key(document: dict[str, object]) -> AlarmResolutionKey:
    return AlarmResolutionKey(
        alarm_configuration_revision=document['alarm_configuration_revision'],
        confirmed_tool_catalog_revision=document['confirmed_tool_catalog_revision'],
    )


# Preserva la AlarmResolutionKey y el plan lógico, no la sesión ejecutable en memoria.
def runtime_to_document(configuration: RuntimeAlarmConfiguration) -> dict[str, object]:
    return {
        'resolution_key': _json_value(configuration.resolution_key),
        'defined_alarm_identities': [
            _identity(identity) for identity in configuration.defined_alarm_identities
        ],
        'planned_alarms': [_json_value(alarm) for alarm in configuration.planned_alarms],
        'parameters_by_alarm': [
            {'identity': _identity(identity), 'parameters': _json_value(parameters)}
            for identity, parameters in sorted(configuration.parameters_by_alarm.items())
        ],
    }


# Reconstituye las entidades tipadas después de la validación física del artifact.
def runtime_from_document(document: dict[str, object]) -> RuntimeAlarmConfiguration:
    planned = []
    for entry in document['planned_alarms']:
        routing = entry['routing']
        deactivation = entry['deactivation_policy']
        planned.append(
            PlannedAlarm(
                identity=_decode_identity(entry['identity']),
                kind=AlarmKind(entry['kind']),
                criticality=Criticality(entry['criticality']),
                priority_group=entry['priority_group'],
                priority_order=entry['priority_order'],
                evaluator_key=entry['evaluator_key'],
                alarm_configuration_revision=entry['alarm_configuration_revision'],
                tool_registry_revision=entry['tool_registry_revision'],
                routing=AlarmRouting(
                    origin_tool_key=routing['origin_tool_key'],
                    destinations=tuple(
                        RoutingDestination(
                            tool_key=destination['tool_key'],
                            delay_seconds=destination['delay_seconds'],
                        )
                        for destination in routing['destinations']
                    ),
                ),
                deactivation_policy=(
                    None
                    if deactivation is None
                    else DeactivationPolicy(approval_required=deactivation['approval_required'])
                ),
                reappearance_after_seconds=entry['reappearance_after_seconds'],
                reappearance_special_conditions=tuple(
                    _decode_identity(identity)
                    for identity in entry['reappearance_special_conditions']
                ),
            )
        )
    return RuntimeAlarmConfiguration(
        resolution_key=_key(document['resolution_key']),
        defined_alarm_identities=tuple(
            _decode_identity(identity) for identity in document['defined_alarm_identities']
        ),
        planned_alarms=tuple(planned),
        parameters_by_alarm={
            _decode_identity(entry['identity']): entry['parameters']
            for entry in document['parameters_by_alarm']
        },
    )


# Ambos artifact usan el mismo tratamiento JSON de enums y dataclasses.
def delivery_to_document(configuration: DeliveryAlarmConfiguration) -> dict[str, object]:
    return _json_value(configuration)


# Entrega la configuración de Delivery vinculada a la misma resolución exacta.
def delivery_from_document(document: dict[str, object]) -> DeliveryAlarmConfiguration:
    alarms = []
    for entry in document['alarms']:
        deactivation = entry['default_deactivation_policy']
        alarms.append(
            ResolvedDeliveryAlarm(
                identity=_decode_identity(entry['identity']),
                is_active=entry['is_active'],
                visibility_mode=VisibilityMode(entry['visibility_mode']),
                display_name=entry['display_name'],
                title=entry['title'],
                cause_template=entry['cause_template'],
                kind=AlarmKind(entry['kind']),
                criticality=Criticality(entry['criticality']),
                business_category=BusinessCategory(entry['business_category']),
                operational_areas=tuple(
                    OperationalArea(area) for area in entry['operational_areas']
                ),
                color=AlarmColor(entry['color']),
                default_deactivation_policy=ResolvedDeactivationPolicy(**deactivation),
                messages=tuple(
                    ResolvedDeliveryMessage(
                        message_key=message['message_key'],
                        display_text=message['display_text'],
                        deactivation_policy=ResolvedDeactivationPolicy(
                            **message['deactivation_policy']
                        ),
                    )
                    for message in entry['messages']
                ),
                visual_targets=tuple(
                    ResolvedVisualTarget(
                        tool_key=target['tool_key'],
                        tool_kind=ToolConfigurationKind(target['tool_kind']),
                        component_keys=tuple(target['component_keys']),
                        subcomponents=tuple(
                            ResolvedVisualSubcomponentTarget(**subcomponent)
                            for subcomponent in target['subcomponents']
                        ),
                        process_projection_mode=(
                            None
                            if target['process_projection_mode'] is None
                            else ProcessAlarmProjectionMode(target['process_projection_mode'])
                        ),
                    )
                    for target in entry['visual_targets']
                ),
            )
        )
    return DeliveryAlarmConfiguration(
        resolution_key=_key(document['resolution_key']), alarms=tuple(alarms)
    )
