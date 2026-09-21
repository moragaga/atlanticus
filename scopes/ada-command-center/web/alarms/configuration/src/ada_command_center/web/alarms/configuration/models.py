from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ada_command_center.alarms.core import (
    AlarmColor,
    AlarmDeactivationDefinition,
    AlarmDefinition,
    AlarmEscalationDefinition,
    AlarmEscalationStepDefinition,
    AlarmIdentity,
    AlarmKind,
    AlarmVisualSubcomponentTarget,
    AlarmVisualTarget,
    BusinessCategory,
    Criticality,
    MessageDeactivationDefinition,
    MessageDefinition,
    MessageScope,
    OperationalArea,
    ProcessAlarmProjectionMode,
    ReappearanceDefinition,
    VisibilityMode,
)
from ada_command_center.web.alarms.configuration.errors import (
    AlarmConfigurationValidationError,
)


@dataclass(frozen=True, slots=True)
class AlarmConfiguration:
    rules: tuple[AlarmDefinition, ...]
    messages: tuple[MessageDefinition, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.rules, tuple):
            raise AlarmConfigurationValidationError('Alarm Configuration rules must be a tuple')
        if not isinstance(self.messages, tuple):
            raise AlarmConfigurationValidationError('Alarm Configuration messages must be a tuple')
        for rule in self.rules:
            if not isinstance(rule, AlarmDefinition):
                raise AlarmConfigurationValidationError(
                    'Alarm Configuration rules must contain AlarmDefinition values'
                )
        for message in self.messages:
            if not isinstance(message, MessageDefinition):
                raise AlarmConfigurationValidationError(
                    'Alarm Configuration messages must contain MessageDefinition values'
                )
        self._validate_rule_identity()
        self._validate_rule_names()
        self._validate_priority_groups()
        messages_by_key = self._index_messages()
        rules_by_identity = {rule.identity: rule for rule in self.rules}
        self._validate_message_references(messages_by_key)
        self._validate_special_condition_references(rules_by_identity)

    def to_document(self) -> dict[str, object]:
        return {
            'rules': [_alarm_definition_to_document(rule) for rule in self.rules],
            'messages': [_message_definition_to_document(message) for message in self.messages],
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> AlarmConfiguration:
        try:
            raw_rules = document['rules']
            raw_messages = document['messages']
            if not isinstance(raw_rules, list) or not isinstance(raw_messages, list):
                raise TypeError
            rules = tuple(_alarm_definition_from_document(item) for item in raw_rules)
            messages = tuple(_message_definition_from_document(item) for item in raw_messages)
            return cls(rules=rules, messages=messages)
        except AlarmConfigurationValidationError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise AlarmConfigurationValidationError(
                'Alarm Configuration document contract is invalid'
            ) from error

    def _validate_rule_identity(self) -> None:
        seen: set[AlarmIdentity] = set()
        for rule in self.rules:
            if rule.identity in seen:
                raise AlarmConfigurationValidationError(
                    f'Duplicate Alarm Configuration identity: {rule.identity.canonical_key}'
                )
            seen.add(rule.identity)

    def _validate_rule_names(self) -> None:
        seen: set[tuple[str, str]] = set()
        for rule in self.rules:
            key = (rule.identity.family_key, rule.rule_name)
            if key in seen:
                raise AlarmConfigurationValidationError(
                    'Alarm Configuration rule_name must be unique within family'
                )
            seen.add(key)

    def _validate_priority_groups(self) -> None:
        groups: dict[str, list[AlarmDefinition]] = {}
        for rule in self.rules:
            groups.setdefault(rule.priority_group, []).append(rule)
        for priority_group, rules in groups.items():
            orders: set[int] = set()
            impact_orders: list[int] = []
            risk_orders: list[int] = []
            for rule in rules:
                if rule.priority_order in orders:
                    raise AlarmConfigurationValidationError(
                        f'priority_order must be unique within priority_group {priority_group}'
                    )
                orders.add(rule.priority_order)
                if rule.kind is AlarmKind.IMPACT:
                    impact_orders.append(rule.priority_order)
                elif rule.kind is AlarmKind.RISK:
                    risk_orders.append(rule.priority_order)
            if impact_orders and risk_orders and max(impact_orders) >= min(risk_orders):
                raise AlarmConfigurationValidationError(
                    f'All IMPACT priority orders must precede RISK in priority_group {priority_group}'
                )

    def _index_messages(self) -> dict[str, MessageDefinition]:
        messages_by_key: dict[str, MessageDefinition] = {}
        for message in self.messages:
            if message.message_key in messages_by_key:
                raise AlarmConfigurationValidationError(
                    f'Duplicate Alarm Configuration message_key: {message.message_key}'
                )
            messages_by_key[message.message_key] = message
        return messages_by_key

    def _validate_message_references(
        self,
        messages_by_key: Mapping[str, MessageDefinition],
    ) -> None:
        for rule in self.rules:
            for message_key in rule.message_keys:
                message = messages_by_key.get(message_key)
                if message is None:
                    raise AlarmConfigurationValidationError(
                        f'Alarm rule references unknown message_key: {message_key}'
                    )
                if (
                    message.scope is MessageScope.FAMILY
                    and message.family_key != rule.identity.family_key
                ):
                    raise AlarmConfigurationValidationError(
                        'Alarm rule may reference only GLOBAL messages or messages from its family'
                    )

    def _validate_special_condition_references(
        self,
        rules_by_identity: Mapping[AlarmIdentity, AlarmDefinition],
    ) -> None:
        for rule in self.rules:
            for identity in rule.reappearance.special_conditions:
                referenced = rules_by_identity.get(identity)
                if referenced is None:
                    raise AlarmConfigurationValidationError(
                        'Alarm rule references an unknown special condition'
                    )
                if not referenced.is_special_condition:
                    raise AlarmConfigurationValidationError(
                        'Alarm rule special condition reference must target a special condition'
                    )
                if referenced.identity.family_key != rule.identity.family_key:
                    raise AlarmConfigurationValidationError(
                        'Alarm rule special condition must belong to the same family'
                    )
                if referenced.priority_group != rule.priority_group:
                    raise AlarmConfigurationValidationError(
                        'Alarm rule special condition must belong to the same priority_group'
                    )


def _alarm_definition_to_document(rule: AlarmDefinition) -> dict[str, object]:
    return {
        'identity': _alarm_identity_to_document(rule.identity),
        'rule_name': rule.rule_name,
        'display_name': rule.display_name,
        'title': rule.title,
        'cause_template': rule.cause_template,
        'is_active': rule.is_active,
        'visibility_mode': rule.visibility_mode.value,
        'is_special_condition': rule.is_special_condition,
        'kind': rule.kind.value,
        'criticality': rule.criticality.value,
        'business_category': rule.business_category.value,
        'operational_areas': [area.value for area in rule.operational_areas],
        'color': rule.color.value,
        'evaluator_key': rule.evaluator_key,
        'parameters': dict(rule.parameters),
        'priority_group': rule.priority_group,
        'priority_order': rule.priority_order,
        'message_keys': list(rule.message_keys),
        'reappearance': _reappearance_to_document(rule.reappearance),
        'default_deactivation': _alarm_deactivation_to_document(rule.default_deactivation),
        'escalation': _escalation_to_document(rule.escalation),
        'visual_targets': [_visual_target_to_document(target) for target in rule.visual_targets],
    }


def _alarm_definition_from_document(document: object) -> AlarmDefinition:
    value = _require_mapping(document)
    parameters = _require_mapping(value['parameters'])
    operational_areas = _require_list(value['operational_areas'])
    message_keys = _require_list(value['message_keys'])
    visual_targets = _require_list(value['visual_targets'])
    return AlarmDefinition(
        identity=_alarm_identity_from_document(value['identity']),
        rule_name=_require_string(value['rule_name']),
        display_name=_require_string(value['display_name']),
        title=_require_string(value['title']),
        cause_template=_require_string(value['cause_template']),
        is_active=_require_bool(value['is_active']),
        visibility_mode=VisibilityMode(_require_string(value['visibility_mode'])),
        is_special_condition=_require_bool(value['is_special_condition']),
        kind=AlarmKind(_require_string(value['kind'])),
        criticality=Criticality(_require_string(value['criticality'])),
        business_category=BusinessCategory(_require_string(value['business_category'])),
        operational_areas=tuple(
            OperationalArea(_require_string(item)) for item in operational_areas
        ),
        color=AlarmColor(_require_string(value['color'])),
        evaluator_key=_require_string(value['evaluator_key']),
        parameters={
            _require_string(key): _require_parameter_value(parameter_value)
            for key, parameter_value in parameters.items()
        },
        priority_group=_require_string(value['priority_group']),
        priority_order=_require_int(value['priority_order']),
        message_keys=tuple(_require_string(item) for item in message_keys),
        reappearance=_reappearance_from_document(value['reappearance']),
        default_deactivation=_alarm_deactivation_from_document(value['default_deactivation']),
        escalation=_escalation_from_document(value['escalation']),
        visual_targets=tuple(_visual_target_from_document(item) for item in visual_targets),
    )


def _message_definition_to_document(message: MessageDefinition) -> dict[str, object]:
    return {
        'message_key': message.message_key,
        'scope': message.scope.value,
        'family_key': message.family_key,
        'display_text': message.display_text,
        'is_active': message.is_active,
        'deactivation_override': (
            _message_deactivation_to_document(message.deactivation_override)
            if message.deactivation_override is not None
            else None
        ),
    }


def _message_definition_from_document(document: object) -> MessageDefinition:
    value = _require_mapping(document)
    raw_override = value.get('deactivation_override')
    raw_family_key = value.get('family_key')
    return MessageDefinition(
        message_key=_require_string(value['message_key']),
        scope=MessageScope(_require_string(value['scope'])),
        family_key=None if raw_family_key is None else _require_string(raw_family_key),
        display_text=_require_string(value['display_text']),
        is_active=_require_bool(value['is_active']),
        deactivation_override=(
            None if raw_override is None else _message_deactivation_from_document(raw_override)
        ),
    )


def _alarm_identity_to_document(identity: AlarmIdentity) -> dict[str, str]:
    return {
        'family_key': identity.family_key,
        'alarm_key': identity.alarm_key,
    }


def _alarm_identity_from_document(document: object) -> AlarmIdentity:
    value = _require_mapping(document)
    return AlarmIdentity(
        family_key=_require_string(value['family_key']),
        alarm_key=_require_string(value['alarm_key']),
    )


def _reappearance_to_document(value: ReappearanceDefinition) -> dict[str, object]:
    return {
        'after_minutes': value.after_minutes,
        'special_conditions': [
            _alarm_identity_to_document(identity) for identity in value.special_conditions
        ],
    }


def _reappearance_from_document(document: object) -> ReappearanceDefinition:
    value = _require_mapping(document)
    special_conditions = _require_list(value.get('special_conditions', []))
    raw_after_minutes = value.get('after_minutes')
    return ReappearanceDefinition(
        after_minutes=(None if raw_after_minutes is None else _require_int(raw_after_minutes)),
        special_conditions=tuple(
            _alarm_identity_from_document(item) for item in special_conditions
        ),
    )


def _alarm_deactivation_to_document(value: AlarmDeactivationDefinition) -> dict[str, object]:
    return {
        'enabled': value.enabled,
        'max_duration_hours': value.max_duration_hours,
        'approval_required': value.approval_required,
    }


def _alarm_deactivation_from_document(document: object) -> AlarmDeactivationDefinition:
    value = _require_mapping(document)
    raw_max_duration = value.get('max_duration_hours')
    return AlarmDeactivationDefinition(
        enabled=_require_bool(value['enabled']),
        max_duration_hours=(None if raw_max_duration is None else _require_int(raw_max_duration)),
        approval_required=_require_bool(value['approval_required']),
    )


def _message_deactivation_to_document(value: MessageDeactivationDefinition) -> dict[str, object]:
    return {
        'enabled': value.enabled,
        'max_duration_hours': value.max_duration_hours,
        'approval_required': value.approval_required,
    }


def _message_deactivation_from_document(document: object) -> MessageDeactivationDefinition:
    value = _require_mapping(document)
    raw_max_duration = value.get('max_duration_hours')
    return MessageDeactivationDefinition(
        enabled=_require_bool(value['enabled']),
        max_duration_hours=(None if raw_max_duration is None else _require_int(raw_max_duration)),
        approval_required=_require_bool(value['approval_required']),
    )


def _escalation_to_document(value: AlarmEscalationDefinition) -> dict[str, object]:
    return {
        'origin_tool_key': value.origin_tool_key,
        'steps': [
            {
                'step_order': step.step_order,
                'target_tool_key': step.target_tool_key,
                'is_enabled': step.is_enabled,
                'wait_minutes_from_previous_step': step.wait_minutes_from_previous_step,
            }
            for step in value.steps
        ],
    }


def _escalation_from_document(document: object) -> AlarmEscalationDefinition:
    value = _require_mapping(document)
    raw_steps = _require_list(value.get('steps', []))
    steps: list[AlarmEscalationStepDefinition] = []
    for raw_step in raw_steps:
        step = _require_mapping(raw_step)
        raw_wait = step.get('wait_minutes_from_previous_step')
        steps.append(
            AlarmEscalationStepDefinition(
                step_order=_require_int(step['step_order']),
                target_tool_key=_require_string(step['target_tool_key']),
                is_enabled=_require_bool(step['is_enabled']),
                wait_minutes_from_previous_step=(
                    None if raw_wait is None else _require_int(raw_wait)
                ),
            )
        )
    return AlarmEscalationDefinition(
        origin_tool_key=_require_string(value['origin_tool_key']),
        steps=tuple(steps),
    )


def _visual_target_to_document(value: AlarmVisualTarget) -> dict[str, object]:
    return {
        'tool_key': value.tool_key,
        'component_keys': list(value.component_keys),
        'subcomponents': [
            {
                'owner_component_key': subcomponent.owner_component_key,
                'subcomponent_key': subcomponent.subcomponent_key,
            }
            for subcomponent in value.subcomponents
        ],
        'process_projection_mode': (
            value.process_projection_mode.value
            if value.process_projection_mode is not None
            else None
        ),
    }


def _visual_target_from_document(document: object) -> AlarmVisualTarget:
    value = _require_mapping(document)
    component_keys = _require_list(value.get('component_keys', []))
    raw_subcomponents = _require_list(value.get('subcomponents', []))
    raw_projection_mode = value.get('process_projection_mode')
    subcomponents: list[AlarmVisualSubcomponentTarget] = []
    for raw_subcomponent in raw_subcomponents:
        subcomponent = _require_mapping(raw_subcomponent)
        subcomponents.append(
            AlarmVisualSubcomponentTarget(
                owner_component_key=_require_string(subcomponent['owner_component_key']),
                subcomponent_key=_require_string(subcomponent['subcomponent_key']),
            )
        )
    return AlarmVisualTarget(
        tool_key=_require_string(value['tool_key']),
        component_keys=tuple(_require_string(item) for item in component_keys),
        subcomponents=tuple(subcomponents),
        process_projection_mode=(
            None
            if raw_projection_mode is None
            else ProcessAlarmProjectionMode(_require_string(raw_projection_mode))
        ),
    )


def _require_mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError
    for key in value:
        if not isinstance(key, str):
            raise TypeError
    return value


def _require_list(value: object) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError
    return value


def _require_string(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError
    return value


def _require_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError
    return value


def _require_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError
    return value


def _require_parameter_value(value: object) -> str | float | bool:
    if isinstance(value, (bool, str, float)):
        return value
    raise TypeError
