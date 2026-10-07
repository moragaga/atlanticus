from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from ada.alarms.core import (
    AffectedInputIssue,
    AlarmEvaluation,
    AlarmStatus,
    EvaluationContext,
    EvaluationError,
    EvaluationErrorOrigin,
    execute_evaluator,
)
from ada.processes.alarm_runtime.session import AlarmExecutionEntry, AlarmExecutionSession
from atlanticus.operational_data.core import normalize_utc_second
from atlanticus.operational_data.planner import DataInputLoadPlan
from atlanticus.operational_data.sources import (
    DataSourcesError,
    DataSourceUnavailableError,
    LoadedDataInputs,
)


@runtime_checkable
class AlarmDataInputLoader(Protocol):
    def load(self, *, plan: DataInputLoadPlan, as_of: datetime) -> LoadedDataInputs: ...


@runtime_checkable
class AlarmEvaluationCycleExecutor(Protocol):
    def run(self, session: AlarmExecutionSession) -> AlarmEvaluationCycleResult: ...


@dataclass(frozen=True, slots=True)
class AlarmEvaluationCycleResult:
    cycle_at: datetime
    evaluations: tuple[AlarmEvaluation, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'cycle_at',
            normalize_utc_second(self.cycle_at, field_name='cycle_at'),
        )
        if not isinstance(self.evaluations, tuple) or not all(
            isinstance(item, AlarmEvaluation) for item in self.evaluations
        ):
            raise TypeError('evaluations must contain AlarmEvaluation values')
        if any(item.evaluated_at != self.cycle_at for item in self.evaluations):
            raise ValueError('all evaluations must use the frozen cycle_at')


@dataclass(slots=True)
class AlarmEvaluationCycle:
    loader: AlarmDataInputLoader
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC).replace(microsecond=0))

    def __post_init__(self) -> None:
        if not isinstance(self.loader, AlarmDataInputLoader):
            raise TypeError('loader must implement AlarmDataInputLoader')
        if not callable(self.clock):
            raise TypeError('clock must be callable')

    def run(self, session: AlarmExecutionSession) -> AlarmEvaluationCycleResult:
        if not isinstance(session, AlarmExecutionSession):
            raise TypeError('session must be an AlarmExecutionSession')
        cycle_at = normalize_utc_second(self.clock(), field_name='cycle_at')
        loaded = self.loader.load(plan=session.data_plan, as_of=cycle_at)
        if not isinstance(loaded, LoadedDataInputs):
            raise TypeError('loader must return LoadedDataInputs')
        if loaded.plan != session.data_plan:
            raise ValueError('loaded inputs plan must match the execution session data plan')
        if loaded.as_of != cycle_at:
            raise ValueError('loaded inputs as_of must match the frozen cycle_at')
        evaluations = tuple(
            self._evaluate(entry=entry, loaded=loaded, cycle_at=cycle_at)
            for entry in session.entries
        )
        expected = tuple(entry.identity for entry in session.entries)
        actual = tuple(item.alarm_identity for item in evaluations)
        if actual != expected:
            raise ValueError('evaluations must exactly follow execution session alarm order')
        return AlarmEvaluationCycleResult(cycle_at=cycle_at, evaluations=evaluations)

    @staticmethod
    def _evaluate(
        *,
        entry: AlarmExecutionEntry,
        loaded: LoadedDataInputs,
        cycle_at: datetime,
    ) -> AlarmEvaluation:
        try:
            data = loaded.context_for(entry.consumer_key)
        except DataSourcesError as error:
            return _input_error(entry=entry, cycle_at=cycle_at, error=error)
        return execute_evaluator(
            entry.planned_alarm,
            EvaluationContext(
                alarm_identity=entry.identity,
                now=cycle_at,
                parameters=entry.parameters,
                data=data,
            ),
            entry.evaluator,
        )


def _input_error(
    *,
    entry: AlarmExecutionEntry,
    cycle_at: datetime,
    error: DataSourcesError,
) -> AlarmEvaluation:
    affected_inputs: tuple[AffectedInputIssue, ...] = ()
    if isinstance(error, DataSourceUnavailableError):
        affected_inputs = (
            AffectedInputIssue(
                reason_key='source_unavailable',
                source_key=error.source.value,
            ),
        )
    return AlarmEvaluation(
        alarm_identity=entry.identity,
        status=AlarmStatus.ERROR,
        evaluated_at=cycle_at,
        error=EvaluationError(
            origin=EvaluationErrorOrigin.RUNTIME,
            error_key='input_preparation_failed',
            message='Evaluation input could not be prepared',
            affected_inputs=affected_inputs,
        ),
    )
