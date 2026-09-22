# Espejo pedagógico de los contratos Runtime materializados.
# defined_alarm_identities conserva DISABLED != REMOVED; planned_alarms contiene sólo Rules ejecutables.
# parameters_by_alarm sólo puede referir alarms ejecutables y no incorpora callables ni planes de datos.

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ada_command_center.alarms.core import AlarmResolutionKey, PlannedAlarm
from ada_command_center.domain.alarms import AlarmIdentity

AlarmParameterValue = str | float | bool


@dataclass(frozen=True, slots=True)
class RuntimeAlarmConfiguration:
    resolution_key: AlarmResolutionKey
    defined_alarm_identities: tuple[AlarmIdentity, ...]
    planned_alarms: tuple[PlannedAlarm, ...]
    parameters_by_alarm: Mapping[AlarmIdentity, Mapping[str, AlarmParameterValue]]

    def __post_init__(self) -> None:
        if not isinstance(self.resolution_key, AlarmResolutionKey):
            raise TypeError('resolution_key must be an AlarmResolutionKey')
        if not isinstance(self.defined_alarm_identities, tuple):
            raise TypeError('defined_alarm_identities must be a tuple')
        defined: set[AlarmIdentity] = set()
        for identity in self.defined_alarm_identities:
            if not isinstance(identity, AlarmIdentity):
                raise TypeError('defined_alarm_identities must contain AlarmIdentity values')
            if identity in defined:
                raise ValueError('defined_alarm_identities must not contain duplicates')
            defined.add(identity)
        if not isinstance(self.planned_alarms, tuple):
            raise TypeError('planned_alarms must be a tuple')
        planned: set[AlarmIdentity] = set()
        for alarm in self.planned_alarms:
            if not isinstance(alarm, PlannedAlarm):
                raise TypeError('planned_alarms must contain PlannedAlarm values')
            if alarm.identity in planned:
                raise ValueError('planned_alarms must not contain duplicate alarm identities')
            if alarm.identity not in defined:
                raise ValueError(
                    'planned alarm identity must be defined by the runtime configuration'
                )
            if (
                alarm.alarm_configuration_revision
                != self.resolution_key.alarm_configuration_revision
            ):
                raise ValueError('planned alarm configuration revision must match resolution_key')
            if alarm.tool_registry_revision != self.resolution_key.confirmed_tool_catalog_revision:
                raise ValueError('planned alarm tool revision must match resolution_key')
            planned.add(alarm.identity)
        if not isinstance(self.parameters_by_alarm, Mapping):
            raise TypeError('parameters_by_alarm must be a mapping')
        normalized: dict[AlarmIdentity, Mapping[str, AlarmParameterValue]] = {}
        for identity, parameters in self.parameters_by_alarm.items():
            if not isinstance(identity, AlarmIdentity):
                raise TypeError('parameters_by_alarm keys must be AlarmIdentity values')
            if identity not in planned:
                raise ValueError('parameters may only be provided for planned alarms')
            normalized[identity] = _normalize_parameters(parameters)
        object.__setattr__(
            self,
            'parameters_by_alarm',
            MappingProxyType(normalized),
        )


def _normalize_parameters(
    values: Mapping[str, AlarmParameterValue],
) -> Mapping[str, AlarmParameterValue]:
    if not isinstance(values, Mapping):
        raise TypeError('alarm parameters must be a mapping')
    normalized: dict[str, AlarmParameterValue] = {}
    for key, value in values.items():
        _require_non_empty_string(key, 'parameter key')
        if not isinstance(value, bool | str | float):
            raise TypeError('parameter values must be TEXT, FLOAT, or BOOLEAN')
        normalized[key] = value
    return MappingProxyType(normalized)


def _require_non_empty_string(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f'{name} must be a string')
    if not value.strip():
        raise ValueError(f'{name} must not be empty')
