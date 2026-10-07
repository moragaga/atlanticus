from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ada.alarms.core import AlarmResolutionKey, Evaluator, PlannedAlarm
from ada.alarms.materialization import EngineAlarmConfiguration
from ada.contracts.alarms import AlarmIdentity
from ada.processes.alarm_runtime.errors import AlarmExecutionSessionError

AlarmParameterValue = str | float | bool


@dataclass(frozen=True, slots=True)
class AlarmEvaluatorContract:
    family_key: str
    evaluator_key: str
    evaluator: Evaluator

    def __post_init__(self) -> None:
        _require_text(self.family_key, 'family_key')
        _require_text(self.evaluator_key, 'evaluator_key')
        if not callable(self.evaluator):
            raise TypeError('evaluator must be callable')

    @property
    def key(self) -> tuple[str, str]:
        return self.family_key, self.evaluator_key


@dataclass(frozen=True, slots=True)
class AlarmEvaluatorRegistry:
    contracts: tuple[AlarmEvaluatorContract, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.contracts, tuple):
            raise TypeError('contracts must be a tuple')
        keys: set[tuple[str, str]] = set()
        for contract in self.contracts:
            if not isinstance(contract, AlarmEvaluatorContract):
                raise TypeError('contracts must contain AlarmEvaluatorContract values')
            if contract.key in keys:
                raise ValueError(
                    'evaluator contracts must be unique by family_key and evaluator_key'
                )
            keys.add(contract.key)

    def resolve(self, planned_alarm: PlannedAlarm) -> AlarmEvaluatorContract:
        if not isinstance(planned_alarm, PlannedAlarm):
            raise TypeError('planned_alarm must be a PlannedAlarm')
        key = planned_alarm.identity.family_key, planned_alarm.evaluator_key
        for contract in self.contracts:
            if contract.key == key:
                return contract
        raise AlarmExecutionSessionError(
            f'{planned_alarm.identity.canonical_key}: evaluator contract is not registered: '
            f'{key[0]}/{key[1]}'
        )


@dataclass(frozen=True, slots=True)
class AlarmExecutionEntry:
    planned_alarm: PlannedAlarm
    evaluator: Evaluator
    parameters: Mapping[str, AlarmParameterValue]

    def __post_init__(self) -> None:
        if not isinstance(self.planned_alarm, PlannedAlarm):
            raise TypeError('planned_alarm must be a PlannedAlarm')
        if not callable(self.evaluator):
            raise TypeError('evaluator must be callable')
        object.__setattr__(self, 'parameters', _normalize_parameters(self.parameters))

    @property
    def identity(self) -> AlarmIdentity:
        return self.planned_alarm.identity


@dataclass(frozen=True, slots=True)
class AlarmExecutionSession:
    configuration: EngineAlarmConfiguration
    entries: tuple[AlarmExecutionEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, EngineAlarmConfiguration):
            raise TypeError('configuration must be an EngineAlarmConfiguration')
        if not isinstance(self.entries, tuple):
            raise TypeError('entries must be a tuple')
        identities: list[AlarmIdentity] = []
        for entry in self.entries:
            if not isinstance(entry, AlarmExecutionEntry):
                raise TypeError('entries must contain AlarmExecutionEntry values')
            identities.append(entry.identity)
        expected = tuple(alarm.identity for alarm in self.configuration.planned_alarms)
        if tuple(identities) != expected:
            raise AlarmExecutionSessionError(
                'execution session entries must exactly follow configured planned alarms'
            )

    @property
    def resolution_key(self) -> AlarmResolutionKey:
        return self.configuration.resolution_key

    @property
    def planned_alarms(self) -> tuple[PlannedAlarm, ...]:
        return self.configuration.planned_alarms

    def entry_for(self, identity: AlarmIdentity) -> AlarmExecutionEntry:
        if not isinstance(identity, AlarmIdentity):
            raise TypeError('identity must be an AlarmIdentity')
        for entry in self.entries:
            if entry.identity == identity:
                return entry
        raise AlarmExecutionSessionError(
            f'{identity.canonical_key}: alarm is not part of the execution session'
        )


def build_alarm_execution_session(
    *,
    configuration: EngineAlarmConfiguration,
    evaluator_registry: AlarmEvaluatorRegistry,
) -> AlarmExecutionSession:
    if not isinstance(configuration, EngineAlarmConfiguration):
        raise TypeError('configuration must be an EngineAlarmConfiguration')
    if not isinstance(evaluator_registry, AlarmEvaluatorRegistry):
        raise TypeError('evaluator_registry must be an AlarmEvaluatorRegistry')
    entries: list[AlarmExecutionEntry] = []
    for planned_alarm in configuration.planned_alarms:
        contract = evaluator_registry.resolve(planned_alarm)
        entries.append(
            AlarmExecutionEntry(
                planned_alarm=planned_alarm,
                evaluator=contract.evaluator,
                parameters=configuration.parameters_by_alarm.get(planned_alarm.identity, {}),
            )
        )
    return AlarmExecutionSession(configuration=configuration, entries=tuple(entries))


def _normalize_parameters(
    values: Mapping[str, AlarmParameterValue],
) -> Mapping[str, AlarmParameterValue]:
    if not isinstance(values, Mapping):
        raise TypeError('parameters must be a mapping')
    normalized: dict[str, AlarmParameterValue] = {}
    for key, value in values.items():
        _require_text(key, 'parameter key')
        if not isinstance(value, bool | str | float):
            raise TypeError('parameter values must be TEXT, FLOAT, or BOOLEAN')
        normalized[key] = value
    return MappingProxyType(normalized)


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f'{name} must be non-empty text without surrounding whitespace')
    return value
