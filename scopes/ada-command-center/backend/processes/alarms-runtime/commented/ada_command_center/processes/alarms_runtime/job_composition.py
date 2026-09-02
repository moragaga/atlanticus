# Espejo comentado: Shell estable que delega scheduling, lease, recovery y drain a Job Runtime.
# Mantiene exactamente los mismos tokens ejecutables que el archivo productivo.

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from ada_command_center.processes.alarms_runtime.composition import AlarmRuntimeComposition
from atlanticus.runtime import (
    JobDefinition,
    JobRuntimeContext,
    RuntimeExecutionResult,
    execute_job,
)

DEFAULT_ALARM_RUNTIME_ITERATION_PERIOD_SECONDS = 5.0
_RECOVERY_MEMORY_KEY = 'ada_command_center.alarms.runtime.job_composition.recovered'


class AlarmRuntimeJobCompositionError(RuntimeError):
    pass


class AlarmRuntimeJobAdoptionOutcome(StrEnum):
    NOT_REQUIRED = 'not_required'
    BOOTSTRAPPED = 'bootstrapped'
    ADOPTED = 'adopted'
    REJECTED = 'rejected'


@dataclass(frozen=True, slots=True)
class AlarmRuntimeJobIterationResult:
    adoption_outcome: AlarmRuntimeJobAdoptionOutcome
    cycle_executed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.adoption_outcome, AlarmRuntimeJobAdoptionOutcome):
            raise TypeError('adoption_outcome must be an AlarmRuntimeJobAdoptionOutcome')
        if not isinstance(self.cycle_executed, bool):
            raise TypeError('cycle_executed must be a bool')

    @property
    def immediate_next_iteration(self) -> bool:
        return (
            self.adoption_outcome is AlarmRuntimeJobAdoptionOutcome.ADOPTED
            and not self.cycle_executed
        )


@runtime_checkable
class AlarmRuntimeIterationExecutor(Protocol):
    def execute(self, context: JobRuntimeContext) -> AlarmRuntimeJobIterationResult: ...


@dataclass(slots=True)
class AlarmRuntimeJobComposition:
    composition: AlarmRuntimeComposition
    iteration_executor: AlarmRuntimeIterationExecutor

    def __post_init__(self) -> None:
        if not isinstance(self.composition, AlarmRuntimeComposition):
            raise TypeError('composition must be an AlarmRuntimeComposition')
        if not isinstance(self.iteration_executor, AlarmRuntimeIterationExecutor):
            raise TypeError('iteration_executor must implement AlarmRuntimeIterationExecutor')

    def recover(self, context: JobRuntimeContext):
        if not isinstance(context, JobRuntimeContext):
            raise TypeError('context must be a JobRuntimeContext')
        result = self.composition.recover(context)
        context.set_memory(_RECOVERY_MEMORY_KEY, self)
        return result

    def drain(self, context: JobRuntimeContext):
        if not isinstance(context, JobRuntimeContext):
            raise TypeError('context must be a JobRuntimeContext')
        context.assert_lease_current()
        self._require_recovered(context)
        return self.composition.reconcile_drain(context)

    def iteration(self, context: JobRuntimeContext) -> AlarmRuntimeJobIterationResult:
        if not isinstance(context, JobRuntimeContext):
            raise TypeError('context must be a JobRuntimeContext')
        context.assert_lease_current()
        self._require_recovered(context)
        result = self.iteration_executor.execute(context)
        if not isinstance(result, AlarmRuntimeJobIterationResult):
            raise TypeError('iteration_executor must return AlarmRuntimeJobIterationResult')
        context.set_iteration_fact('adoption_outcome', result.adoption_outcome.value)
        context.set_iteration_fact('cycle_executed', result.cycle_executed)
        if result.immediate_next_iteration:
            context.set_next_iteration_delay(0)
        return result

    def _require_recovered(self, context: JobRuntimeContext) -> None:
        if context.get_memory(_RECOVERY_MEMORY_KEY) is not self:
            raise AlarmRuntimeJobCompositionError(
                'Alarm Engine recovery hook must complete before job iteration'
            )
        if not self.composition.durability.persistence.read_head().aligned:
            raise AlarmRuntimeJobCompositionError(
                'Alarm Engine journal must be recovered before job iteration'
            )


def execute_alarm_runtime_job(
    *,
    definition: JobDefinition,
    composition: AlarmRuntimeJobComposition,
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> RuntimeExecutionResult:
    if not isinstance(definition, JobDefinition):
        raise TypeError('definition must be a JobDefinition')
    if not isinstance(composition, AlarmRuntimeJobComposition):
        raise TypeError('composition must be an AlarmRuntimeJobComposition')
    return execute_job(
        definition=definition,
        recovery=composition.recover,
        iteration=composition.iteration,
        drain=composition.drain,
        argv=argv,
        environ=environ,
    )
