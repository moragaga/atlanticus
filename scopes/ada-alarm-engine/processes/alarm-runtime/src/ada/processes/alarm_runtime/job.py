from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from ada.alarms.materialization import EngineAlarmConfiguration
from ada.alarms.persistence import AlarmMaterializationPersistenceError
from ada.processes.alarm_runtime.errors import (
    AlarmExecutionSessionError,
    AlarmRuntimeConfigurationError,
)
from ada.processes.alarm_runtime.session import (
    AlarmEvaluatorRegistry,
    AlarmExecutionSession,
    build_alarm_execution_session,
)
from atlanticus.runtime import JobRuntimeContext

INITIAL_CONFIGURATION_RETRY_SECONDS = 30.0
_SESSION_MEMORY_KEY = 'ada.alarm_engine.runtime.execution_session'


@runtime_checkable
class EngineConfigurationReader(Protocol):
    def read_published_engine(self, *, source_key: str) -> EngineAlarmConfiguration | None: ...


class AlarmRuntimeConfigurationOutcome(StrEnum):
    WAITING = 'WAITING'
    BOOTSTRAPPED = 'BOOTSTRAPPED'
    ADOPTED = 'ADOPTED'
    UNCHANGED = 'UNCHANGED'
    REJECTED = 'REJECTED'


@dataclass(frozen=True, slots=True)
class AlarmRuntimeIterationResult:
    outcome: AlarmRuntimeConfigurationOutcome
    session: AlarmExecutionSession | None
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, AlarmRuntimeConfigurationOutcome):
            raise TypeError('outcome must be an AlarmRuntimeConfigurationOutcome')
        if self.session is not None and not isinstance(self.session, AlarmExecutionSession):
            raise TypeError('session must be an AlarmExecutionSession or None')
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError('reason must be non-empty text')


class AlarmRuntimeJob:
    def __init__(
        self,
        *,
        reader: EngineConfigurationReader,
        source_key: str,
        evaluator_registry: AlarmEvaluatorRegistry,
    ) -> None:
        if not isinstance(reader, EngineConfigurationReader):
            raise TypeError('reader must implement EngineConfigurationReader')
        if not isinstance(source_key, str) or not source_key or source_key.strip() != source_key:
            raise ValueError('source_key must be non-empty text without surrounding whitespace')
        if not isinstance(evaluator_registry, AlarmEvaluatorRegistry):
            raise TypeError('evaluator_registry must be an AlarmEvaluatorRegistry')
        self._reader = reader
        self._source_key = source_key
        self._evaluator_registry = evaluator_registry

    def run_iteration(self, context: JobRuntimeContext) -> AlarmRuntimeIterationResult:
        context.raise_if_cancelled()
        pinned = context.get_memory(_SESSION_MEMORY_KEY)
        if pinned is not None and not isinstance(pinned, AlarmExecutionSession):
            raise TypeError('pinned execution session must be an AlarmExecutionSession')
        try:
            configuration = self._reader.read_published_engine(source_key=self._source_key)
        except AlarmMaterializationPersistenceError:
            if pinned is None:
                raise
            result = AlarmRuntimeIterationResult(
                outcome=AlarmRuntimeConfigurationOutcome.REJECTED,
                session=pinned,
                reason='published_engine_invalid_using_pinned',
            )
            self._record(context, result)
            return result

        if configuration is None:
            if pinned is None:
                context.set_next_iteration_delay(INITIAL_CONFIGURATION_RETRY_SECONDS)
                result = AlarmRuntimeIterationResult(
                    outcome=AlarmRuntimeConfigurationOutcome.WAITING,
                    session=None,
                    reason='published_engine_missing',
                )
                self._record(context, result)
                return result
            result = AlarmRuntimeIterationResult(
                outcome=AlarmRuntimeConfigurationOutcome.UNCHANGED,
                session=pinned,
                reason='published_engine_missing_using_pinned',
            )
            self._record(context, result)
            return result

        if pinned is not None and configuration.resolution_key == pinned.resolution_key:
            if configuration != pinned.configuration:
                raise AlarmRuntimeConfigurationError(
                    'Published Engine configuration changed without changing resolution_key'
                )
            result = AlarmRuntimeIterationResult(
                outcome=AlarmRuntimeConfigurationOutcome.UNCHANGED,
                session=pinned,
                reason='published_engine_unchanged',
            )
            self._record(context, result)
            return result

        try:
            candidate = build_alarm_execution_session(
                configuration=configuration,
                evaluator_registry=self._evaluator_registry,
            )
        except AlarmExecutionSessionError:
            if pinned is None:
                context.set_next_iteration_delay(INITIAL_CONFIGURATION_RETRY_SECONDS)
            result = AlarmRuntimeIterationResult(
                outcome=AlarmRuntimeConfigurationOutcome.REJECTED,
                session=pinned,
                reason='published_engine_not_executable',
            )
            self._record(context, result)
            return result

        context.raise_if_cancelled()
        context.set_memory(_SESSION_MEMORY_KEY, candidate)
        context.mark_iteration_work()
        result = AlarmRuntimeIterationResult(
            outcome=(
                AlarmRuntimeConfigurationOutcome.BOOTSTRAPPED
                if pinned is None
                else AlarmRuntimeConfigurationOutcome.ADOPTED
            ),
            session=candidate,
            reason='published_engine_adopted',
        )
        self._record(context, result)
        return result

    @staticmethod
    def _record(context: JobRuntimeContext, result: AlarmRuntimeIterationResult) -> None:
        context.set_iteration_fact('outcome', result.outcome.value)
        context.set_iteration_fact('reason', result.reason)
        if result.session is not None:
            key = result.session.resolution_key
            context.set_iteration_fact(
                'alarm_configuration_revision', key.alarm_configuration_revision
            )
            context.set_iteration_fact('tool_catalog_revision', key.confirmed_tool_catalog_revision)
            context.set_iteration_fact('planned_alarm_count', len(result.session.entries))
