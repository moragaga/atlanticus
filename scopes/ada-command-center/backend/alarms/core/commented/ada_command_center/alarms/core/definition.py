# Espejo pedagógico de los contratos fuente editables de una Rule de alarma.
# Este módulo no resuelve referencias externas ni modifica contratos de runtime.
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from ada_command_center.alarms.core.models import AlarmIdentity, AlarmKind, Criticality


class BusinessCategory(StrEnum):
    ECOLOGY = 'ECOLOGY'
    PRODUCTIVITY = 'PRODUCTIVITY'
    SAFETY_HEALTH = 'SAFETY_HEALTH'
    COSTS = 'COSTS'


class AlarmColor(StrEnum):
    RED = 'RED'
    YELLOW = 'YELLOW'


class OperationalArea(StrEnum):
    MINE = 'MINE'
    PLANT = 'PLANT'


class VisibilityMode(StrEnum):
    VISIBLE = 'VISIBLE'
    TRACE_ONLY = 'TRACE_ONLY'


class MessageScope(StrEnum):
    GLOBAL = 'GLOBAL'
    FAMILY = 'FAMILY'


class ProcessAlarmProjectionMode(StrEnum):
    GENERIC = 'GENERIC'
    DISTRIBUTED = 'DISTRIBUTED'


@dataclass(frozen=True, slots=True)
class AlarmDeactivationDefinition:
    enabled: bool
    max_duration_hours: int | None
    approval_required: bool

    def __post_init__(self) -> None:
        _validate_deactivation_definition(
            enabled=self.enabled,
            max_duration_hours=self.max_duration_hours,
            approval_required=self.approval_required,
        )


@dataclass(frozen=True, slots=True)
class MessageDeactivationDefinition:
    enabled: bool
    max_duration_hours: int | None
    approval_required: bool

    def __post_init__(self) -> None:
        _validate_deactivation_definition(
            enabled=self.enabled,
            max_duration_hours=self.max_duration_hours,
            approval_required=self.approval_required,
        )


@dataclass(frozen=True, slots=True)
class ReappearanceDefinition:
    after_minutes: int | None = None
    special_conditions: tuple[AlarmIdentity, ...] = ()

    def __post_init__(self) -> None:
        if self.after_minutes is not None:
            _require_int(self.after_minutes, 'after_minutes')
            if self.after_minutes <= 0:
                raise ValueError('after_minutes must be greater than zero')
        if not isinstance(self.special_conditions, tuple):
            raise TypeError('special_conditions must be a tuple')
        seen: set[AlarmIdentity] = set()
        for identity in self.special_conditions:
            if not isinstance(identity, AlarmIdentity):
                raise TypeError('special_conditions must contain AlarmIdentity values')
            if identity in seen:
                raise ValueError('special_conditions must not contain duplicates')
            seen.add(identity)


@dataclass(frozen=True, slots=True)
class AlarmEscalationStepDefinition:
    step_order: int
    target_tool_key: str
    is_enabled: bool
    wait_minutes_from_previous_step: int | None = None

    def __post_init__(self) -> None:
        _require_int(self.step_order, 'step_order')
        if self.step_order <= 0:
            raise ValueError('step_order must be greater than zero')
        _require_non_empty_string(self.target_tool_key, 'target_tool_key')
        _require_bool(self.is_enabled, 'is_enabled')
        if self.wait_minutes_from_previous_step is not None:
            _require_int(
                self.wait_minutes_from_previous_step,
                'wait_minutes_from_previous_step',
            )
            if self.wait_minutes_from_previous_step < 0:
                raise ValueError('wait_minutes_from_previous_step must not be negative')


@dataclass(frozen=True, slots=True)
class AlarmEscalationDefinition:
    origin_tool_key: str
    steps: tuple[AlarmEscalationStepDefinition, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty_string(self.origin_tool_key, 'origin_tool_key')
        if not isinstance(self.steps, tuple):
            raise TypeError('steps must be a tuple')
        seen_orders: set[int] = set()
        seen_targets: set[str] = {self.origin_tool_key}
        for step in self.steps:
            if not isinstance(step, AlarmEscalationStepDefinition):
                raise TypeError('steps must contain AlarmEscalationStepDefinition values')
            if step.step_order in seen_orders:
                raise ValueError('step_order must be unique within escalation')
            if step.target_tool_key in seen_targets:
                raise ValueError('escalation tool targets must not contain duplicates')
            seen_orders.add(step.step_order)
            seen_targets.add(step.target_tool_key)


@dataclass(frozen=True, slots=True, order=True)
class AlarmVisualSubcomponentTarget:
    owner_component_key: str
    subcomponent_key: str

    def __post_init__(self) -> None:
        _require_non_empty_string(self.owner_component_key, 'owner_component_key')
        _require_non_empty_string(self.subcomponent_key, 'subcomponent_key')


@dataclass(frozen=True, slots=True)
class AlarmVisualTarget:
    tool_key: str
    component_keys: tuple[str, ...] = ()
    subcomponents: tuple[AlarmVisualSubcomponentTarget, ...] = ()
    process_projection_mode: ProcessAlarmProjectionMode | None = None

    def __post_init__(self) -> None:
        _require_non_empty_string(self.tool_key, 'tool_key')
        if not isinstance(self.component_keys, tuple):
            raise TypeError('component_keys must be a tuple')
        seen_components: set[str] = set()
        for component_key in self.component_keys:
            _require_non_empty_string(component_key, 'component_key')
            if component_key in seen_components:
                raise ValueError('component_keys must not contain duplicates')
            seen_components.add(component_key)
        if not isinstance(self.subcomponents, tuple):
            raise TypeError('subcomponents must be a tuple')
        seen_subcomponents: set[tuple[str, str]] = set()
        for subcomponent in self.subcomponents:
            if not isinstance(subcomponent, AlarmVisualSubcomponentTarget):
                raise TypeError(
                    'subcomponents must contain AlarmVisualSubcomponentTarget values'
                )
            identity = (
                subcomponent.owner_component_key,
                subcomponent.subcomponent_key,
            )
            if identity in seen_subcomponents:
                raise ValueError('subcomponents must not contain duplicates')
            seen_subcomponents.add(identity)
        if self.process_projection_mode is not None and not isinstance(
            self.process_projection_mode,
            ProcessAlarmProjectionMode,
        ):
            raise TypeError(
                'process_projection_mode must be a ProcessAlarmProjectionMode'
            )


@dataclass(frozen=True, slots=True)
class MessageDefinition:
    message_key: str
    scope: MessageScope
    display_text: str
    is_active: bool
    family_key: str | None = None
    deactivation_override: MessageDeactivationDefinition | None = None

    def __post_init__(self) -> None:
        _require_non_empty_string(self.message_key, 'message_key')
        if not isinstance(self.scope, MessageScope):
            raise TypeError('scope must be a MessageScope')
        _require_non_empty_string(self.display_text, 'display_text')
        _require_bool(self.is_active, 'is_active')
        if self.scope is MessageScope.GLOBAL:
            if self.family_key is not None:
                raise ValueError('GLOBAL message must not define family_key')
        else:
            _require_non_empty_string(self.family_key, 'family_key')
        if self.deactivation_override is not None and not isinstance(
            self.deactivation_override,
            MessageDeactivationDefinition,
        ):
            raise TypeError(
                'deactivation_override must be a MessageDeactivationDefinition'
            )


@dataclass(frozen=True, slots=True)
class AlarmDefinition:
    identity: AlarmIdentity
    rule_name: str
    display_name: str
    title: str
    cause_template: str
    is_active: bool
    visibility_mode: VisibilityMode
    is_special_condition: bool
    kind: AlarmKind
    criticality: Criticality
    business_category: BusinessCategory
    operational_areas: tuple[OperationalArea, ...]
    color: AlarmColor
    evaluator_key: str
    parameters: Mapping[str, str | float | bool]
    priority_group: str
    priority_order: int
    message_keys: tuple[str, ...]
    reappearance: ReappearanceDefinition
    default_deactivation: AlarmDeactivationDefinition
    escalation: AlarmEscalationDefinition
    visual_targets: tuple[AlarmVisualTarget, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, AlarmIdentity):
            raise TypeError('identity must be an AlarmIdentity')
        _require_non_empty_string(self.rule_name, 'rule_name')
        _require_non_empty_string(self.display_name, 'display_name')
        _require_non_empty_string(self.title, 'title')
        _require_non_empty_string(self.cause_template, 'cause_template')
        _require_bool(self.is_active, 'is_active')
        if not isinstance(self.visibility_mode, VisibilityMode):
            raise TypeError('visibility_mode must be a VisibilityMode')
        _require_bool(self.is_special_condition, 'is_special_condition')
        if not isinstance(self.kind, AlarmKind):
            raise TypeError('kind must be an AlarmKind')
        if not isinstance(self.criticality, Criticality):
            raise TypeError('criticality must be a Criticality')
        if not isinstance(self.business_category, BusinessCategory):
            raise TypeError('business_category must be a BusinessCategory')
        self._validate_operational_areas()
        if not isinstance(self.color, AlarmColor):
            raise TypeError('color must be an AlarmColor')
        _require_non_empty_string(self.evaluator_key, 'evaluator_key')
        self._normalize_parameters()
        _require_non_empty_string(self.priority_group, 'priority_group')
        _require_int(self.priority_order, 'priority_order')
        if self.priority_order <= 0:
            raise ValueError('priority_order must be greater than zero')
        self._validate_message_keys()
        if not isinstance(self.reappearance, ReappearanceDefinition):
            raise TypeError('reappearance must be a ReappearanceDefinition')
        if not isinstance(self.default_deactivation, AlarmDeactivationDefinition):
            raise TypeError(
                'default_deactivation must be an AlarmDeactivationDefinition'
            )
        if not isinstance(self.escalation, AlarmEscalationDefinition):
            raise TypeError('escalation must be an AlarmEscalationDefinition')
        self._validate_visual_targets()

    def _validate_operational_areas(self) -> None:
        if not isinstance(self.operational_areas, tuple):
            raise TypeError('operational_areas must be a tuple')
        if not self.operational_areas:
            raise ValueError('operational_areas must not be empty')
        seen: set[OperationalArea] = set()
        for area in self.operational_areas:
            if not isinstance(area, OperationalArea):
                raise TypeError('operational_areas must contain OperationalArea values')
            if area in seen:
                raise ValueError('operational_areas must not contain duplicates')
            seen.add(area)

    def _normalize_parameters(self) -> None:
        if not isinstance(self.parameters, Mapping):
            raise TypeError('parameters must be a mapping')
        normalized: dict[str, str | float | bool] = {}
        for key, value in self.parameters.items():
            _require_non_empty_string(key, 'parameter key')
            if isinstance(value, (bool, str, float)):
                normalized[key] = value
            else:
                raise TypeError('parameter values must be TEXT, FLOAT, or BOOLEAN')
        object.__setattr__(self, 'parameters', MappingProxyType(normalized))

    def _validate_message_keys(self) -> None:
        if not isinstance(self.message_keys, tuple):
            raise TypeError('message_keys must be a tuple')
        seen: set[str] = set()
        for message_key in self.message_keys:
            _require_non_empty_string(message_key, 'message_key')
            if message_key in seen:
                raise ValueError('message_keys must not contain duplicates')
            seen.add(message_key)

    def _validate_visual_targets(self) -> None:
        if not isinstance(self.visual_targets, tuple):
            raise TypeError('visual_targets must be a tuple')
        seen_tools: set[str] = set()
        for target in self.visual_targets:
            if not isinstance(target, AlarmVisualTarget):
                raise TypeError('visual_targets must contain AlarmVisualTarget values')
            if target.tool_key in seen_tools:
                raise ValueError('visual_targets must not repeat tool_key')
            seen_tools.add(target.tool_key)


def _validate_deactivation_definition(
    *,
    enabled: bool,
    max_duration_hours: int | None,
    approval_required: bool,
) -> None:
    _require_bool(enabled, 'enabled')
    _require_bool(approval_required, 'approval_required')
    if not enabled:
        if max_duration_hours is not None:
            raise ValueError('disabled deactivation must not define max_duration_hours')
        if approval_required:
            raise ValueError('disabled deactivation must not require approval')
        return
    if max_duration_hours is None:
        raise ValueError('enabled deactivation requires max_duration_hours')
    _require_int(max_duration_hours, 'max_duration_hours')
    if not 1 <= max_duration_hours <= 12:
        raise ValueError('max_duration_hours must be between 1 and 12')


def _require_non_empty_string(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f'{name} must be a string')
    if not value.strip():
        raise ValueError(f'{name} must not be empty')


def _require_bool(value: object, name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f'{name} must be a bool')


def _require_int(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f'{name} must be an int')
