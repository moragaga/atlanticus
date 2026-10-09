# Espejo pedagógico en español; la lógica es equivalente al archivo productivo.
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ada.alarms.core import (
    AlarmEvaluation,
    AlarmResolutionKey,
    AlarmStatus,
    EvaluationContext,
    EvaluationError,
    EvaluationErrorOrigin,
    Evaluator,
    PlannedAlarm,
)
from ada.alarms.materialization import EngineAlarmConfiguration
from ada.contracts.alarms import AlarmIdentity
from ada.processes.alarm_runtime.errors import AlarmExecutionSessionError
from atlanticus.operational_data.core import DataInputSpec, validate_data_inputs
from atlanticus.operational_data.planner import DataInputLoadPlan, DataInputPlanner

AlarmParameterValue = str | float | bool


@dataclass(frozen=True, slots=True)
# Cada evaluador declara identidad ejecutable e inputs operacionales independientes.
class AlarmEvaluatorContract:
    family_key: str
    evaluator_key: str
    evaluator: Evaluator
    inputs: tuple[DataInputSpec, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.family_key, 'family_key')
        _require_text(self.evaluator_key, 'evaluator_key')
        if not callable(self.evaluator):
            raise TypeError('evaluator must be callable')
        object.__setattr__(self, 'inputs', validate_data_inputs(tuple(self.inputs)))

    @property
    def key(self) -> tuple[str, str]:
        return self.family_key, self.evaluator_key


@dataclass(frozen=True, slots=True)
# El registro resuelve pares familia/evaluador; permite descubrir contratos no desplegados.
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

    # La búsqueda no bloqueante posibilita el despliegue desfasado entre código y configuración.
    def find(self, planned_alarm: PlannedAlarm) -> AlarmEvaluatorContract | None:
        if not isinstance(planned_alarm, PlannedAlarm):
            raise TypeError('planned_alarm must be a PlannedAlarm')
        key = planned_alarm.identity.family_key, planned_alarm.evaluator_key
        for contract in self.contracts:
            if contract.key == key:
                return contract
        return None

    def resolve(self, planned_alarm: PlannedAlarm) -> AlarmEvaluatorContract:
        contract = self.find(planned_alarm)
        if contract is not None:
            return contract
        key = planned_alarm.identity.family_key, planned_alarm.evaluator_key
        raise AlarmExecutionSessionError(
            f'{planned_alarm.identity.canonical_key}: evaluator contract is not registered: '
            f'{key[0]}/{key[1]}'
        )


@dataclass(frozen=True, slots=True)
# Una entrada representa una alarma configurada, aun sin contrato disponible en código.
class AlarmExecutionEntry:
    planned_alarm: PlannedAlarm
    evaluator: Evaluator
    parameters: Mapping[str, AlarmParameterValue]
    inputs: tuple[DataInputSpec, ...] = ()
    contract_available: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.contract_available, bool):
            raise TypeError('contract_available must be a bool')
        if not isinstance(self.planned_alarm, PlannedAlarm):
            raise TypeError('planned_alarm must be a PlannedAlarm')
        if not callable(self.evaluator):
            raise TypeError('evaluator must be callable')
        object.__setattr__(self, 'parameters', _normalize_parameters(self.parameters))
        object.__setattr__(self, 'inputs', validate_data_inputs(tuple(self.inputs)))

    @property
    def identity(self) -> AlarmIdentity:
        return self.planned_alarm.identity

    @property
    def consumer_key(self) -> str:
        return self.identity.canonical_key


@dataclass(frozen=True, slots=True)
# La sesión retiene todas las alarmas y el plan de datos de las ejecutables.
class AlarmExecutionSession:
    configuration: EngineAlarmConfiguration
    entries: tuple[AlarmExecutionEntry, ...]
    data_plan: DataInputLoadPlan
    unregistered_alarms: tuple[AlarmIdentity, ...] = ()
    unreferenced_contracts: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.unregistered_alarms, tuple):
            raise TypeError('unregistered_alarms must be a tuple')
        if not isinstance(self.unreferenced_contracts, tuple):
            raise TypeError('unreferenced_contracts must be a tuple')
        if not isinstance(self.configuration, EngineAlarmConfiguration):
            raise TypeError('configuration must be an EngineAlarmConfiguration')
        if not isinstance(self.entries, tuple):
            raise TypeError('entries must be a tuple')
        if not isinstance(self.data_plan, DataInputLoadPlan):
            raise TypeError('data_plan must be a DataInputLoadPlan')
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
        expected_consumers = tuple(entry.consumer_key for entry in self.entries)
        if tuple(self.data_plan.inputs_by_key) != expected_consumers:
            raise AlarmExecutionSessionError(
                'data plan consumers must exactly follow execution session alarm order'
            )
        for entry in self.entries:
            if self.data_plan.inputs_for(entry.consumer_key) != entry.inputs:
                raise AlarmExecutionSessionError(
                    f'{entry.consumer_key}: data plan inputs do not match evaluator contract'
                )
        missing = tuple(entry.identity for entry in self.entries if not entry.contract_available)
        if self.unregistered_alarms != missing:
            raise AlarmExecutionSessionError('missing contract identities do not match session')
        if self.unreferenced_contracts != tuple(sorted(set(self.unreferenced_contracts))):
            raise AlarmExecutionSessionError('unreferenced evaluator contracts must be unique and sorted')

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


# Reconcilia el Engine publicado con el registro actual, sin omitir identidades.
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
    missing: list[AlarmIdentity] = []
    referenced: set[tuple[str, str]] = set()
    inputs_by_key: dict[str, tuple[DataInputSpec, ...]] = {}
    for planned_alarm in configuration.planned_alarms:
        key = planned_alarm.identity.family_key, planned_alarm.evaluator_key
        referenced.add(key)
        contract = evaluator_registry.find(planned_alarm)
        available = contract is not None
        if contract is None:
            missing.append(planned_alarm.identity)
        entry = AlarmExecutionEntry(
            planned_alarm=planned_alarm,
            evaluator=_unavailable_evaluator if contract is None else contract.evaluator,
            parameters=configuration.parameters_by_alarm.get(planned_alarm.identity, {}),
            inputs=() if contract is None else contract.inputs,
            contract_available=available,
        )
        entries.append(entry)
        inputs_by_key[entry.consumer_key] = entry.inputs
    return AlarmExecutionSession(
        configuration=configuration,
        entries=tuple(entries),
        data_plan=DataInputPlanner().plan(inputs_by_key),
        unregistered_alarms=tuple(missing),
        unreferenced_contracts=tuple(
            sorted(contract.key for contract in evaluator_registry.contracts if contract.key not in referenced)
        ),
    )


# No inventa INACTIVE: la falta de código se transforma en ERROR técnico auditable.
def _unavailable_evaluator(context: EvaluationContext) -> AlarmEvaluation:
    return AlarmEvaluation(
        alarm_identity=context.alarm_identity,
        status=AlarmStatus.ERROR,
        evaluated_at=context.now,
        error=EvaluationError(
            origin=EvaluationErrorOrigin.RUNTIME,
            error_key='evaluator_contract_unavailable',
            message='Evaluator contract is not registered in this deployment',
        ),
    )


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
