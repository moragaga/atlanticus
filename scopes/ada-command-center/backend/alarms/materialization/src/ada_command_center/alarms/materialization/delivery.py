from __future__ import annotations

from dataclasses import dataclass

from ada.web.tools.enums import ToolConfigurationKind
from ada_command_center.alarms.core import AlarmResolutionKey
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


@dataclass(frozen=True, slots=True)
class ResolvedDeactivationPolicy:
    enabled: bool
    max_duration_hours: int | None
    approval_required: bool

    def __post_init__(self) -> None:
        _require_bool(self.enabled, 'enabled')
        _require_bool(self.approval_required, 'approval_required')
        if not self.enabled:
            if self.max_duration_hours is not None:
                raise ValueError('disabled deactivation must not define max_duration_hours')
            if self.approval_required:
                raise ValueError('disabled deactivation must not require approval')
            return
        if self.max_duration_hours is None:
            raise ValueError('enabled deactivation requires max_duration_hours')
        _require_int(self.max_duration_hours, 'max_duration_hours')
        if not 1 <= self.max_duration_hours <= 12:
            raise ValueError('max_duration_hours must be between 1 and 12')


@dataclass(frozen=True, slots=True)
class ResolvedDeliveryMessage:
    message_key: str
    display_text: str
    deactivation_policy: ResolvedDeactivationPolicy

    def __post_init__(self) -> None:
        _require_non_empty_string(self.message_key, 'message_key')
        _require_non_empty_string(self.display_text, 'display_text')
        if not isinstance(self.deactivation_policy, ResolvedDeactivationPolicy):
            raise TypeError('deactivation_policy must be a ResolvedDeactivationPolicy')


@dataclass(frozen=True, slots=True, order=True)
class ResolvedVisualSubcomponentTarget:
    owner_component_key: str
    subcomponent_key: str

    def __post_init__(self) -> None:
        _require_non_empty_string(self.owner_component_key, 'owner_component_key')
        _require_non_empty_string(self.subcomponent_key, 'subcomponent_key')


@dataclass(frozen=True, slots=True)
class ResolvedVisualTarget:
    tool_key: str
    tool_kind: ToolConfigurationKind
    component_keys: tuple[str, ...] = ()
    subcomponents: tuple[ResolvedVisualSubcomponentTarget, ...] = ()
    process_projection_mode: ProcessAlarmProjectionMode | None = None

    def __post_init__(self) -> None:
        _require_non_empty_string(self.tool_key, 'tool_key')
        if not isinstance(self.tool_kind, ToolConfigurationKind):
            raise TypeError('tool_kind must be a ToolConfigurationKind')
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
        seen_subcomponents: set[ResolvedVisualSubcomponentTarget] = set()
        for subcomponent in self.subcomponents:
            if not isinstance(subcomponent, ResolvedVisualSubcomponentTarget):
                raise TypeError(
                    'subcomponents must contain ResolvedVisualSubcomponentTarget values'
                )
            if subcomponent in seen_subcomponents:
                raise ValueError('subcomponents must not contain duplicates')
            seen_subcomponents.add(subcomponent)
        if self.process_projection_mode is not None and not isinstance(
            self.process_projection_mode,
            ProcessAlarmProjectionMode,
        ):
            raise TypeError('process_projection_mode must be a ProcessAlarmProjectionMode')


@dataclass(frozen=True, slots=True)
class ResolvedDeliveryAlarm:
    identity: AlarmIdentity
    is_active: bool
    visibility_mode: VisibilityMode
    display_name: str
    title: str
    cause_template: str
    kind: AlarmKind
    criticality: Criticality
    business_category: BusinessCategory
    operational_areas: tuple[OperationalArea, ...]
    color: AlarmColor
    default_deactivation_policy: ResolvedDeactivationPolicy
    messages: tuple[ResolvedDeliveryMessage, ...] = ()
    visual_targets: tuple[ResolvedVisualTarget, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.identity, AlarmIdentity):
            raise TypeError('identity must be an AlarmIdentity')
        _require_bool(self.is_active, 'is_active')
        if not isinstance(self.visibility_mode, VisibilityMode):
            raise TypeError('visibility_mode must be a VisibilityMode')
        _require_non_empty_string(self.display_name, 'display_name')
        _require_non_empty_string(self.title, 'title')
        _require_non_empty_string(self.cause_template, 'cause_template')
        if not isinstance(self.kind, AlarmKind):
            raise TypeError('kind must be an AlarmKind')
        if not isinstance(self.criticality, Criticality):
            raise TypeError('criticality must be a Criticality')
        if not isinstance(self.business_category, BusinessCategory):
            raise TypeError('business_category must be a BusinessCategory')
        _validate_operational_areas(self.operational_areas)
        if not isinstance(self.color, AlarmColor):
            raise TypeError('color must be an AlarmColor')
        if not isinstance(self.default_deactivation_policy, ResolvedDeactivationPolicy):
            raise TypeError('default_deactivation_policy must be a ResolvedDeactivationPolicy')
        _validate_messages(self.messages)
        _validate_visual_targets(self.visual_targets)


@dataclass(frozen=True, slots=True)
class DeliveryAlarmConfiguration:
    resolution_key: AlarmResolutionKey
    alarms: tuple[ResolvedDeliveryAlarm, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.resolution_key, AlarmResolutionKey):
            raise TypeError('resolution_key must be an AlarmResolutionKey')
        if not isinstance(self.alarms, tuple):
            raise TypeError('alarms must be a tuple')
        seen: set[AlarmIdentity] = set()
        for alarm in self.alarms:
            if not isinstance(alarm, ResolvedDeliveryAlarm):
                raise TypeError('alarms must contain ResolvedDeliveryAlarm values')
            if alarm.identity in seen:
                raise ValueError('alarms must not contain duplicate alarm identities')
            seen.add(alarm.identity)


def _validate_operational_areas(values: tuple[OperationalArea, ...]) -> None:
    if not isinstance(values, tuple):
        raise TypeError('operational_areas must be a tuple')
    if not values:
        raise ValueError('operational_areas must not be empty')
    seen: set[OperationalArea] = set()
    for area in values:
        if not isinstance(area, OperationalArea):
            raise TypeError('operational_areas must contain OperationalArea values')
        if area in seen:
            raise ValueError('operational_areas must not contain duplicates')
        seen.add(area)


def _validate_messages(values: tuple[ResolvedDeliveryMessage, ...]) -> None:
    if not isinstance(values, tuple):
        raise TypeError('messages must be a tuple')
    seen: set[str] = set()
    for message in values:
        if not isinstance(message, ResolvedDeliveryMessage):
            raise TypeError('messages must contain ResolvedDeliveryMessage values')
        if message.message_key in seen:
            raise ValueError('messages must not contain duplicate message_key values')
        seen.add(message.message_key)


def _validate_visual_targets(values: tuple[ResolvedVisualTarget, ...]) -> None:
    if not isinstance(values, tuple):
        raise TypeError('visual_targets must be a tuple')
    seen: set[str] = set()
    for target in values:
        if not isinstance(target, ResolvedVisualTarget):
            raise TypeError('visual_targets must contain ResolvedVisualTarget values')
        if target.tool_key in seen:
            raise ValueError('visual_targets must not contain duplicate tool_key values')
        seen.add(target.tool_key)


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
