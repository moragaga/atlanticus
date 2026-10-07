from __future__ import annotations

from dataclasses import dataclass

from ada.contracts.alarms import AlarmIdentity, AlarmKind, Criticality


@dataclass(frozen=True, slots=True, order=True)
class AlarmResolutionKey:
    alarm_configuration_revision: str
    confirmed_tool_catalog_revision: str

    def __post_init__(self) -> None:
        _require_non_empty_string(
            self.alarm_configuration_revision,
            'alarm_configuration_revision',
        )
        _require_non_empty_string(
            self.confirmed_tool_catalog_revision,
            'confirmed_tool_catalog_revision',
        )


@dataclass(frozen=True, slots=True, order=True)
class RoutingDestination:
    tool_key: str
    delay_seconds: int | None = None

    def __post_init__(self) -> None:
        _require_non_empty_string(self.tool_key, 'tool_key')
        if self.delay_seconds is None:
            return
        if isinstance(self.delay_seconds, bool) or not isinstance(self.delay_seconds, int):
            raise TypeError('delay_seconds must be an int')
        if self.delay_seconds < 0:
            raise ValueError('delay_seconds must not be negative')


@dataclass(frozen=True, slots=True)
class AlarmRouting:
    origin_tool_key: str
    destinations: tuple[RoutingDestination, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty_string(self.origin_tool_key, 'origin_tool_key')
        if not isinstance(self.destinations, tuple):
            raise TypeError('destinations must be a tuple')
        seen = {self.origin_tool_key}
        normalized: list[RoutingDestination] = []
        for destination in self.destinations:
            if not isinstance(destination, RoutingDestination):
                raise TypeError('destinations must contain RoutingDestination values')
            if destination.tool_key in seen:
                raise ValueError('routing tools must not contain duplicates')
            seen.add(destination.tool_key)
            normalized.append(destination)
        object.__setattr__(self, 'destinations', tuple(sorted(normalized)))


@dataclass(frozen=True, slots=True)
class DeactivationPolicy:
    approval_required: bool

    def __post_init__(self) -> None:
        if not isinstance(self.approval_required, bool):
            raise TypeError('approval_required must be a bool')


@dataclass(frozen=True, slots=True)
class PlannedAlarm:
    identity: AlarmIdentity
    kind: AlarmKind
    criticality: Criticality
    priority_group: str
    priority_order: int
    evaluator_key: str
    alarm_configuration_revision: str
    tool_registry_revision: str
    routing: AlarmRouting
    deactivation_policy: DeactivationPolicy | None = None
    reappearance_after_seconds: int | None = None
    reappearance_special_conditions: tuple[AlarmIdentity, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.identity, AlarmIdentity):
            raise TypeError('identity must be an AlarmIdentity')
        if not isinstance(self.kind, AlarmKind):
            raise TypeError('kind must be an AlarmKind')
        if not isinstance(self.criticality, Criticality):
            raise TypeError('criticality must be a Criticality')
        _require_non_empty_string(self.priority_group, 'priority_group')
        if isinstance(self.priority_order, bool) or not isinstance(self.priority_order, int):
            raise TypeError('priority_order must be an int')
        if self.priority_order <= 0:
            raise ValueError('priority_order must be greater than zero')
        _require_non_empty_string(self.evaluator_key, 'evaluator_key')
        _require_non_empty_string(
            self.alarm_configuration_revision,
            'alarm_configuration_revision',
        )
        _require_non_empty_string(self.tool_registry_revision, 'tool_registry_revision')
        if not isinstance(self.routing, AlarmRouting):
            raise TypeError('routing must be an AlarmRouting')
        if self.deactivation_policy is not None and not isinstance(
            self.deactivation_policy,
            DeactivationPolicy,
        ):
            raise TypeError('deactivation_policy must be a DeactivationPolicy')
        if self.reappearance_after_seconds is not None:
            if isinstance(self.reappearance_after_seconds, bool) or not isinstance(
                self.reappearance_after_seconds,
                int,
            ):
                raise TypeError('reappearance_after_seconds must be an int')
            if self.reappearance_after_seconds <= 0:
                raise ValueError('reappearance_after_seconds must be greater than zero')
        if not isinstance(self.reappearance_special_conditions, tuple):
            raise TypeError('reappearance_special_conditions must be a tuple')
        seen_special_conditions: set[AlarmIdentity] = set()
        for identity in self.reappearance_special_conditions:
            if not isinstance(identity, AlarmIdentity):
                raise TypeError('reappearance_special_conditions must contain AlarmIdentity values')
            if identity in seen_special_conditions:
                raise ValueError('reappearance_special_conditions must not contain duplicates')
            seen_special_conditions.add(identity)
        if self.criticality is Criticality.C1 and any(
            destination.delay_seconds is not None for destination in self.routing.destinations
        ):
            raise ValueError('C1 routing destinations must be immediate')
        if self.criticality is Criticality.C2 and any(
            destination.delay_seconds is None for destination in self.routing.destinations
        ):
            raise ValueError('C2 routing destinations require delay_seconds')
        if self.criticality is Criticality.C3 and self.routing.destinations:
            raise ValueError('C3 routing must contain only the origin Tool')


def _require_non_empty_string(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f'{name} must be a string')
    if not value.strip():
        raise ValueError(f'{name} must not be empty')
