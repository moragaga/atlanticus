from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum

from ada.alarms.core import (
    AlarmResolutionKey,
    AlarmRouting,
    DeactivationPolicy,
    PlannedAlarm,
    RoutingDestination,
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
from ada.contracts.alarms import (
    AlarmColor,
    AlarmIdentity,
    AlarmKind,
    BusinessCategory,
    Criticality,
    OperationalArea,
    ProcessAlarmProjectionMode,
    VisibilityMode,
)
from ada.contracts.tools.enums import ToolConfigurationKind


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


def _decode_identity(document: Mapping[str, object]) -> AlarmIdentity:
    return AlarmIdentity(
        family_key=document['family_key'],
        alarm_key=document['alarm_key'],
    )


def _key(document: Mapping[str, object]) -> AlarmResolutionKey:
    return AlarmResolutionKey(
        alarm_configuration_revision=document['alarm_configuration_revision'],
        confirmed_tool_catalog_revision=document['confirmed_tool_catalog_revision'],
    )


def engine_to_document(configuration: EngineAlarmConfiguration) -> dict[str, object]:
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


def engine_from_document(document: Mapping[str, object]) -> EngineAlarmConfiguration:
    planned = []
    for entry in document['planned_alarms']:
        routing = entry['routing']
        deactivation = entry['deactivation_policy']
        planned.append(
            PlannedAlarm(
                identity=_decode_identity(entry['identity']),
                kind=AlarmKind(entry['kind']),
                criticality=Criticality(entry['criticality']),
                is_special_condition=entry['is_special_condition'],
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
    return EngineAlarmConfiguration(
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


def modeler_to_document(configuration: ModelerAlarmConfiguration) -> dict[str, object]:
    return _json_value(configuration)


def modeler_from_document(document: Mapping[str, object]) -> ModelerAlarmConfiguration:
    alarms = []
    for entry in document['alarms']:
        alarms.append(
            ResolvedModelerAlarm(
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
                priority_group=entry['priority_group'],
                priority_order=entry['priority_order'],
                default_deactivation_policy=_deactivation_policy(
                    entry['default_deactivation_policy']
                ),
                messages=tuple(
                    ResolvedModelerMessage(
                        message_key=message['message_key'],
                        display_text=message['display_text'],
                        deactivation_policy=_deactivation_policy(message['deactivation_policy']),
                    )
                    for message in entry['messages']
                ),
                visual_targets=tuple(
                    ResolvedVisualTarget(
                        tool_key=target['tool_key'],
                        tool_kind=ToolConfigurationKind(target['tool_kind']),
                        component_keys=tuple(target['component_keys']),
                        subcomponents=tuple(
                            ResolvedVisualSubcomponentTarget(
                                owner_component_key=subcomponent['owner_component_key'],
                                subcomponent_key=subcomponent['subcomponent_key'],
                            )
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
    return ModelerAlarmConfiguration(
        resolution_key=_key(document['resolution_key']),
        alarms=tuple(alarms),
    )


def delivery_to_document(configuration: DeliveryAlarmConfiguration) -> dict[str, object]:
    return _json_value(configuration)


def delivery_from_document(document: Mapping[str, object]) -> DeliveryAlarmConfiguration:
    return DeliveryAlarmConfiguration(
        resolution_key=_key(document['resolution_key']),
        publication_tool_keys=tuple(document['publication_tool_keys']),
    )


def _deactivation_policy(document: Mapping[str, object]) -> ResolvedDeactivationPolicy:
    return ResolvedDeactivationPolicy(
        enabled=document['enabled'],
        max_duration_hours=document['max_duration_hours'],
        approval_required=document['approval_required'],
    )
