# Espejo pedagógico en español; la lógica es equivalente al archivo productivo.
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol, runtime_checkable

from ada.alarms.materialization import EngineAlarmConfiguration
from ada.alarms.persistence import AlarmMaterializationPersistenceError
from ada.processes.alarm_runtime.adoption import plan_configuration_adoption
from ada.processes.alarm_runtime.cycle import (
    AlarmEvaluationCycleExecutor,
    AlarmEvaluationCycleResult,
)
from ada.processes.alarm_runtime.diagnostics import emit_evaluator_contract_diagnostics
from ada.processes.alarm_runtime.durable_adoption import (
    AlarmDurableAdopter,
    AlarmOperationalAdoptionRequired,
)
from ada.processes.alarm_runtime.durable_commit import AlarmDurableCycleCommitter
from ada.processes.alarm_runtime.durable_recovery import (
    AlarmDurableRecovery,
    RecoveredAlarmAuthority,
)
from ada.processes.alarm_runtime.errors import (
    AlarmExecutionSessionError,
    AlarmRuntimeConfigurationError,
)
from ada.processes.alarm_runtime.lifecycle import (
    AlarmLifecycleCycle,
    AlarmLifecycleCycleExecutor,
    AlarmLifecycleCycleResult,
    AlarmLifecycleRuntimeState,
)
from ada.processes.alarm_runtime.session import (
    AlarmEvaluatorRegistry,
    AlarmExecutionSession,
    build_alarm_execution_session,
)
from atlanticus.operational_data.sources import DataSourceApplications, DataSourceRoutingError
from atlanticus.runtime import JobRuntimeContext

INITIAL_CONFIGURATION_RETRY_SECONDS = 30.0
_SESSION_MEMORY_KEY = 'ada.alarm_engine.runtime.execution_session'
_LIFECYCLE_MEMORY_KEY = 'ada.alarm_engine.runtime.lifecycle_state'
_DURABLE_MEMORY_KEY = 'ada.alarm_engine.runtime.durable_authority'


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
    cycle: AlarmEvaluationCycleResult | None = None
    lifecycle: AlarmLifecycleCycleResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, AlarmRuntimeConfigurationOutcome):
            raise TypeError('outcome must be an AlarmRuntimeConfigurationOutcome')
        if self.session is not None and not isinstance(self.session, AlarmExecutionSession):
            raise TypeError('session must be an AlarmExecutionSession or None')
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError('reason must be non-empty text')
        if self.cycle is not None and not isinstance(self.cycle, AlarmEvaluationCycleResult):
            raise TypeError('cycle must be an AlarmEvaluationCycleResult or None')
        if self.lifecycle is not None and not isinstance(self.lifecycle, AlarmLifecycleCycleResult):
            raise TypeError('lifecycle must be an AlarmLifecycleCycleResult or None')
        if self.cycle is not None and self.session is None:
            raise ValueError('cycle requires an execution session')
        if self.lifecycle is not None:
            if self.cycle is None or self.session is None:
                raise ValueError('lifecycle requires cycle and execution session')
            if self.lifecycle.cycle_at != self.cycle.cycle_at:
                raise ValueError('lifecycle cycle_at must match evaluation cycle_at')
            if self.lifecycle.state.configuration != self.session.configuration:
                raise ValueError('lifecycle state configuration must match execution session')


# Orquesta la adopción y evaluación de alarmas sin comprometer el estado durable.
class AlarmRuntimeJob:
    def __init__(
        self,
        *,
        reader: EngineConfigurationReader,
        source_key: str,
        evaluator_registry: AlarmEvaluatorRegistry,
        source_applications: DataSourceApplications,
        cycle: AlarmEvaluationCycleExecutor,
        lifecycle: AlarmLifecycleCycleExecutor | None = None,
        durable_recovery: AlarmDurableRecovery | None = None,
        durable_committer: AlarmDurableCycleCommitter | None = None,
        durable_adopter: AlarmDurableAdopter | None = None,
    ) -> None:
        if not isinstance(reader, EngineConfigurationReader):
            raise TypeError('reader must implement EngineConfigurationReader')
        if not isinstance(source_key, str) or not source_key or source_key.strip() != source_key:
            raise ValueError('source_key must be non-empty text without surrounding whitespace')
        if not isinstance(evaluator_registry, AlarmEvaluatorRegistry):
            raise TypeError('evaluator_registry must be an AlarmEvaluatorRegistry')
        if not isinstance(source_applications, DataSourceApplications):
            raise TypeError('source_applications must be DataSourceApplications')
        if not isinstance(cycle, AlarmEvaluationCycleExecutor):
            raise TypeError('cycle must implement AlarmEvaluationCycleExecutor')
        resolved_lifecycle = AlarmLifecycleCycle() if lifecycle is None else lifecycle
        if not isinstance(resolved_lifecycle, AlarmLifecycleCycleExecutor):
            raise TypeError('lifecycle must implement AlarmLifecycleCycleExecutor')
        self._reader = reader
        self._source_key = source_key
        self._evaluator_registry = evaluator_registry
        self._source_applications = source_applications
        self._cycle = cycle
        if (durable_recovery is None) != (durable_committer is None):
            raise ValueError('durable recovery and committer must be configured together')
        if durable_recovery is not None and not isinstance(durable_recovery, AlarmDurableRecovery):
            raise TypeError('durable_recovery must be AlarmDurableRecovery')
        if durable_committer is not None and not isinstance(
            durable_committer, AlarmDurableCycleCommitter
        ):
            raise TypeError('durable_committer must be AlarmDurableCycleCommitter')
        self._lifecycle = resolved_lifecycle
        self._durable_recovery = durable_recovery
        if durable_adopter is not None and durable_committer is None:
            raise ValueError('durable adoption requires a durable committer')
        if durable_adopter is not None and not isinstance(durable_adopter, AlarmDurableAdopter):
            raise TypeError('durable_adopter must be AlarmDurableAdopter')
        self._durable_committer = durable_committer
        self._durable_adopter = durable_adopter

    # Reconstruye EFFECTIVE desde WAL y vuelve a asociar los evaluadores del despliegue actual.
    def recover(self, context: JobRuntimeContext) -> RecoveredAlarmAuthority:
        if self._durable_recovery is None:
            raise AlarmRuntimeConfigurationError('durable recovery is not configured')
        recovered = self._durable_recovery.recover(context)
        if recovered.lifecycle is not None:
            session = build_alarm_execution_session(
                configuration=recovered.lifecycle.configuration,
                evaluator_registry=self._evaluator_registry,
            )
            self._source_applications.validate_sources(session.data_plan.sources)
            context.assert_lease_current()
            context.set_memory(_SESSION_MEMORY_KEY, session)
            context.set_memory(_LIFECYCLE_MEMORY_KEY, recovered.lifecycle)
            emit_evaluator_contract_diagnostics(session)
        context.set_memory(_DURABLE_MEMORY_KEY, recovered)
        return recovered

    # Evalúa la configuración publicada; los contratos ausentes no bloquean alarmas disponibles.
    def run_iteration(self, context: JobRuntimeContext) -> AlarmRuntimeIterationResult:
        context.raise_if_cancelled()
        if self._durable_committer is not None:
            recovered = context.get_memory(_DURABLE_MEMORY_KEY)
            if not isinstance(recovered, RecoveredAlarmAuthority):
                raise AlarmRuntimeConfigurationError('durable recovery must run before iterations')
            if self._durable_adopter is not None:
                return self._run_durable_adoption_iteration(context, recovered)
            if recovered.artifact_ref is None:
                context.set_next_iteration_delay(INITIAL_CONFIGURATION_RETRY_SECONDS)
                waiting = AlarmRuntimeIterationResult(
                    outcome=AlarmRuntimeConfigurationOutcome.WAITING,
                    session=None,
                    reason='effective_configuration_missing',
                )
                self._record(context, waiting)
                return waiting
        pinned = context.get_memory(_SESSION_MEMORY_KEY)
        if pinned is not None and not isinstance(pinned, AlarmExecutionSession):
            raise TypeError('pinned execution session must be an AlarmExecutionSession')
        try:
            configuration = self._reader.read_published_engine(source_key=self._source_key)
        except AlarmMaterializationPersistenceError:
            if pinned is None:
                raise
            return self._finish(
                context,
                AlarmRuntimeIterationResult(
                    outcome=AlarmRuntimeConfigurationOutcome.REJECTED,
                    session=pinned,
                    reason='published_engine_invalid_using_pinned',
                ),
            )

        if configuration is None:
            if pinned is None:
                context.set_next_iteration_delay(INITIAL_CONFIGURATION_RETRY_SECONDS)
                return self._finish(
                    context,
                    AlarmRuntimeIterationResult(
                        outcome=AlarmRuntimeConfigurationOutcome.WAITING,
                        session=None,
                        reason='published_engine_missing',
                    ),
                )
            return self._finish(
                context,
                AlarmRuntimeIterationResult(
                    outcome=AlarmRuntimeConfigurationOutcome.UNCHANGED,
                    session=pinned,
                    reason='published_engine_missing_using_pinned',
                ),
            )

        if pinned is not None and configuration.resolution_key == pinned.resolution_key:
            if configuration != pinned.configuration:
                raise AlarmRuntimeConfigurationError(
                    'Published Engine configuration changed without changing resolution_key'
                )
            return self._finish(
                context,
                AlarmRuntimeIterationResult(
                    outcome=AlarmRuntimeConfigurationOutcome.UNCHANGED,
                    session=pinned,
                    reason='published_engine_unchanged',
                ),
            )

        try:
            candidate = build_alarm_execution_session(
                configuration=configuration,
                evaluator_registry=self._evaluator_registry,
            )
            self._source_applications.validate_sources(candidate.data_plan.sources)
        except AlarmExecutionSessionError, DataSourceRoutingError:
            if pinned is None:
                context.set_next_iteration_delay(INITIAL_CONFIGURATION_RETRY_SECONDS)
            return self._finish(
                context,
                AlarmRuntimeIterationResult(
                    outcome=AlarmRuntimeConfigurationOutcome.REJECTED,
                    session=pinned,
                    reason='published_engine_not_executable',
                ),
            )

        if pinned is not None and self._durable_committer is not None:
            return self._finish(
                context,
                AlarmRuntimeIterationResult(
                    outcome=AlarmRuntimeConfigurationOutcome.REJECTED,
                    session=pinned,
                    reason='published_engine_pending_durable_adoption',
                ),
            )
        if pinned is not None:
            adoption = plan_configuration_adoption(pinned.configuration, candidate.configuration)
            if not adoption.is_adoptable:
                return self._finish(
                    context,
                    AlarmRuntimeIterationResult(
                        outcome=AlarmRuntimeConfigurationOutcome.REJECTED,
                        session=pinned,
                        reason='published_engine_not_adoptable',
                    ),
                )

        context.raise_if_cancelled()
        finished = self._finish(
            context,
            AlarmRuntimeIterationResult(
                outcome=(
                    AlarmRuntimeConfigurationOutcome.BOOTSTRAPPED
                    if pinned is None
                    else AlarmRuntimeConfigurationOutcome.ADOPTED
                ),
                session=candidate,
                reason='published_engine_adopted',
            ),
        )
        context.set_memory(_SESSION_MEMORY_KEY, candidate)
        emit_evaluator_contract_diagnostics(candidate)
        context.mark_iteration_work()
        return finished

    # Adopta READY mediante una transacción durable antes de cambiar la sesión en memoria.
    def _run_durable_adoption_iteration(
        self,
        context: JobRuntimeContext,
        recovered: RecoveredAlarmAuthority,
    ) -> AlarmRuntimeIterationResult:
        adopter = self._durable_adopter
        if adopter is None or self._durable_recovery is None:
            raise AlarmRuntimeConfigurationError('durable adoption is not configured')
        pinned = context.get_memory(_SESSION_MEMORY_KEY)
        if pinned is not None and not isinstance(pinned, AlarmExecutionSession):
            raise TypeError('pinned execution session must be AlarmExecutionSession')
        if (recovered.artifact_ref is None) != (pinned is None):
            raise AlarmRuntimeConfigurationError('pinned session differs from durable authority')
        try:
            ready = adopter.read_candidate()
        except AlarmMaterializationPersistenceError:
            if pinned is None:
                context.set_next_iteration_delay(INITIAL_CONFIGURATION_RETRY_SECONDS)
            return self._finish(
                context,
                AlarmRuntimeIterationResult(
                    outcome=AlarmRuntimeConfigurationOutcome.REJECTED,
                    session=pinned,
                    reason='published_ready_invalid_using_effective',
                ),
            )
        if ready is None:
            if pinned is None:
                context.set_next_iteration_delay(INITIAL_CONFIGURATION_RETRY_SECONDS)
            return self._finish(
                context,
                AlarmRuntimeIterationResult(
                    outcome=(
                        AlarmRuntimeConfigurationOutcome.WAITING
                        if pinned is None
                        else AlarmRuntimeConfigurationOutcome.UNCHANGED
                    ),
                    session=pinned,
                    reason='published_ready_missing',
                ),
            )
        target_ref = adopter.reference_for(ready)
        if target_ref == recovered.artifact_ref:
            if pinned is None or pinned.configuration != ready.engine:
                raise AlarmRuntimeConfigurationError('READY differs from pinned EFFECTIVE')
            return self._finish(
                context,
                AlarmRuntimeIterationResult(
                    outcome=AlarmRuntimeConfigurationOutcome.UNCHANGED,
                    session=pinned,
                    reason='effective_configuration_unchanged',
                ),
            )
        if (
            pinned is not None
            and ready.engine.resolution_key == pinned.resolution_key
            and ready.engine != pinned.configuration
        ):
            raise AlarmRuntimeConfigurationError(
                'Published Engine configuration changed without changing resolution_key'
            )
        try:
            candidate = build_alarm_execution_session(
                configuration=ready.engine,
                evaluator_registry=self._evaluator_registry,
            )
            self._source_applications.validate_sources(candidate.data_plan.sources)
        except AlarmExecutionSessionError, DataSourceRoutingError:
            if pinned is None:
                context.set_next_iteration_delay(INITIAL_CONFIGURATION_RETRY_SECONDS)
            return self._finish(
                context,
                AlarmRuntimeIterationResult(
                    outcome=AlarmRuntimeConfigurationOutcome.REJECTED,
                    session=pinned,
                    reason='published_engine_not_executable',
                ),
            )
        if pinned is not None:
            plan = plan_configuration_adoption(pinned.configuration, candidate.configuration)
            if not plan.is_adoptable:
                return self._finish(
                    context,
                    AlarmRuntimeIterationResult(
                        outcome=AlarmRuntimeConfigurationOutcome.REJECTED,
                        session=pinned,
                        reason='published_engine_not_adoptable',
                    ),
                )
        context.raise_if_cancelled()
        current = self._durable_recovery.recover(context)
        if current.artifact_ref != recovered.artifact_ref:
            raise AlarmRuntimeConfigurationError('EFFECTIVE changed before adoption')
        if current.lifecycle != context.get_memory(_LIFECYCLE_MEMORY_KEY):
            raise AlarmRuntimeConfigurationError('lifecycle memory differs from durable recovery')
        try:
            adopter.adopt(context, recovered=current, ready=ready)
        except AlarmOperationalAdoptionRequired:
            return self._finish(
                context,
                AlarmRuntimeIterationResult(
                    outcome=AlarmRuntimeConfigurationOutcome.REJECTED,
                    session=pinned,
                    reason='published_engine_requires_operational_adoption',
                ),
            )
        confirmed = self._durable_recovery.recover(context)
        if confirmed.artifact_ref != target_ref or confirmed.lifecycle is None:
            raise AlarmRuntimeConfigurationError('confirmed EFFECTIVE differs from adopted READY')
        if confirmed.lifecycle.configuration != candidate.configuration:
            raise AlarmRuntimeConfigurationError('confirmed configuration differs from candidate')
        context.assert_lease_current()
        context.set_memory(_SESSION_MEMORY_KEY, candidate)
        context.set_memory(_LIFECYCLE_MEMORY_KEY, confirmed.lifecycle)
        context.set_memory(_DURABLE_MEMORY_KEY, confirmed)
        emit_evaluator_contract_diagnostics(candidate)
        context.mark_iteration_work()
        result = AlarmRuntimeIterationResult(
            outcome=(
                AlarmRuntimeConfigurationOutcome.BOOTSTRAPPED
                if recovered.artifact_ref is None
                else AlarmRuntimeConfigurationOutcome.ADOPTED
            ),
            session=candidate,
            reason='effective_configuration_committed',
        )
        self._record(context, result)
        return result

    # Ejecuta ciclo, lifecycle y commit solo después de disponer de una sesión válida.
    def _finish(
        self,
        context: JobRuntimeContext,
        result: AlarmRuntimeIterationResult,
    ) -> AlarmRuntimeIterationResult:
        if result.session is not None:
            context.raise_if_cancelled()
            cycle = self._cycle.run(result.session)
            previous = context.get_memory(_LIFECYCLE_MEMORY_KEY)
            if previous is not None and not isinstance(previous, AlarmLifecycleRuntimeState):
                raise TypeError('pinned lifecycle state must be an AlarmLifecycleRuntimeState')
            lifecycle = self._lifecycle.run(
                previous=previous,
                session=result.session,
                cycle=cycle,
            )
            if self._durable_committer is not None:
                recovered = context.get_memory(_DURABLE_MEMORY_KEY)
                if not isinstance(recovered, RecoveredAlarmAuthority):
                    raise AlarmRuntimeConfigurationError('durable authority is unavailable')
                if previous is None:
                    raise AlarmRuntimeConfigurationError('durable lifecycle state is unavailable')
                confirmed = self._durable_committer.commit(
                    context,
                    recovered=recovered,
                    previous=previous,
                    cycle=cycle,
                    lifecycle=lifecycle,
                )
                lifecycle = replace(lifecycle, state=confirmed)
            context.set_memory(_LIFECYCLE_MEMORY_KEY, lifecycle.state)
            result = AlarmRuntimeIterationResult(
                outcome=result.outcome,
                session=result.session,
                reason=result.reason,
                cycle=cycle,
                lifecycle=lifecycle,
            )
            if cycle.evaluations:
                context.mark_iteration_work()
        self._record(context, result)
        return result

    @staticmethod
    # Publica hechos resumidos en la iteración para consola y telemetría.
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
            context.set_iteration_fact(
                'missing_evaluator_contract_count', len(result.session.unregistered_alarms)
            )
            context.set_iteration_fact(
                'unreferenced_evaluator_contract_count', len(result.session.unreferenced_contracts)
            )
        if result.cycle is not None:
            evaluations = result.cycle.evaluations
            context.set_iteration_fact('cycle_at_utc', result.cycle.cycle_at.isoformat())
            context.set_iteration_fact('evaluation_count', len(evaluations))
            context.set_iteration_fact(
                'active_evaluation_count',
                sum(item.status.value == 'ACTIVE' for item in evaluations),
            )
            context.set_iteration_fact(
                'inactive_evaluation_count',
                sum(item.status.value == 'INACTIVE' for item in evaluations),
            )
            context.set_iteration_fact(
                'error_evaluation_count',
                sum(item.status.value == 'ERROR' for item in evaluations),
            )
        if result.lifecycle is not None:
            groups = result.lifecycle.groups
            context.set_iteration_fact('lifecycle_group_count', len(groups))
            context.set_iteration_fact(
                'open_technical_incident_count',
                len(result.lifecycle.state.technical_incidents),
            )
            context.set_iteration_fact(
                'technical_incident_change_count',
                len(result.lifecycle.technical_incident_changes),
            )
            context.set_iteration_fact(
                'occurrence_change_count',
                sum(
                    len(item.decision.occurrence_changes)
                    + (
                        0
                        if item.adoption_decision is None
                        else len(item.adoption_decision.occurrence_changes)
                    )
                    for item in groups
                ),
            )
            context.set_iteration_fact(
                'episode_change_count',
                sum(
                    len(item.decision.episode_changes)
                    + (
                        0
                        if item.adoption_decision is None
                        else len(item.adoption_decision.episode_changes)
                    )
                    for item in groups
                ),
            )
            context.set_iteration_fact(
                'management_action_count',
                sum(len(item.decision.management_action_results) for item in groups),
            )
