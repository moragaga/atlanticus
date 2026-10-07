from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ada.alarms.core import (
    AlarmEvaluation,
    AlarmStatus,
    EvaluationError,
    EvaluationErrorOrigin,
    EvidenceSnapshot,
    ManagementAction,
    ManagementActionOutcome,
    OccurrenceClosureReason,
)
from ada.alarms.materialization import EngineAlarmConfiguration
from ada.contracts.alarms import Criticality
from ada.processes.alarm_runtime import (
    AlarmEvaluationCycleResult,
    AlarmLifecycleCycle,
    AlarmLifecycleOrchestrationError,
    AlarmOperationalInputs,
    build_alarm_execution_session,
)

from .support import engine_configuration, registry

AT = datetime(2026, 10, 7, 21, 0, tzinfo=UTC)


class InputsProvider:
    def __init__(self) -> None:
        self.value = AlarmOperationalInputs()
        self.calls = []

    def read(self, *, session, cycle_at):
        self.calls.append((session, cycle_at))
        return self.value


class Ids:
    def __init__(self) -> None:
        self.occurrences = 0
        self.episodes = 0
        self.management_effects = 0
        self.deactivation_requests = 0
        self.deactivation_effects = 0

    def occurrence(self, _identity, _at):
        self.occurrences += 1
        return f'O{self.occurrences}'

    def episode(self, _group, _at):
        self.episodes += 1
        return f'E{self.episodes}'

    def management_effect(self, _action):
        self.management_effects += 1
        return f'ME{self.management_effects}'

    def deactivation_request(self, _action):
        self.deactivation_requests += 1
        return f'DR{self.deactivation_requests}'

    def deactivation_effect(self, _request):
        self.deactivation_effects += 1
        return f'DE{self.deactivation_effects}'


def _configuration_with_plan(configuration, plan) -> EngineAlarmConfiguration:
    return EngineAlarmConfiguration(
        resolution_key=configuration.resolution_key,
        defined_alarm_identities=configuration.defined_alarm_identities,
        planned_alarms=(plan,),
        parameters_by_alarm=configuration.parameters_by_alarm,
    )


def _session(configuration):
    return build_alarm_execution_session(
        configuration=configuration,
        evaluator_registry=registry(),
    )


def _evaluation(session, status: AlarmStatus, *, at: datetime) -> AlarmEvaluation:
    identity = session.entries[0].identity
    if status is AlarmStatus.ERROR:
        return AlarmEvaluation(
            alarm_identity=identity,
            status=status,
            evaluated_at=at,
            error=EvaluationError(
                origin=EvaluationErrorOrigin.QUALITY,
                error_key='insufficient_samples',
                message='Insufficient samples',
            ),
        )
    return AlarmEvaluation(
        alarm_identity=identity,
        status=status,
        evaluated_at=at,
        evidence_snapshot=EvidenceSnapshot(
            contract_key='test',
            contract_version='1',
            payload={},
        ),
    )


def _cycle(session, status: AlarmStatus, *, at: datetime) -> AlarmEvaluationCycleResult:
    return AlarmEvaluationCycleResult(
        cycle_at=at,
        evaluations=(_evaluation(session, status, at=at),),
    )


def _lifecycle(provider=None):
    ids = Ids()
    return (
        AlarmLifecycleCycle(
            inputs_provider=InputsProvider() if provider is None else provider,
            occurrence_id_factory=ids.occurrence,
            episode_id_factory=ids.episode,
            management_effect_id_factory=ids.management_effect,
            deactivation_request_id_factory=ids.deactivation_request,
            deactivation_effect_id_factory=ids.deactivation_effect,
        ),
        ids,
    )


def test_active_evaluation_opens_occurrence_and_shared_episode() -> None:
    session = _session(engine_configuration())
    lifecycle, _ids = _lifecycle()

    result = lifecycle.run(
        previous=None,
        session=session,
        cycle=_cycle(session, AlarmStatus.ACTIVE, at=AT),
    )

    assert len(result.groups) == 1
    group = result.groups[0]
    assert group.adoption_decision is None
    assert group.decision.state.episode is not None
    runtime = group.decision.state.get(session.entries[0].identity)
    assert runtime is not None and runtime.occurrence is not None
    assert runtime.occurrence.occurrence_id == 'O1'
    assert runtime.occurrence.episode_id == 'E1'
    assert result.state.groups == (group.decision.state,)


def test_repeated_active_preserves_open_occurrence() -> None:
    session = _session(engine_configuration())
    lifecycle, _ids = _lifecycle()
    first = lifecycle.run(
        previous=None,
        session=session,
        cycle=_cycle(session, AlarmStatus.ACTIVE, at=AT),
    )

    second = lifecycle.run(
        previous=first.state,
        session=session,
        cycle=_cycle(session, AlarmStatus.ACTIVE, at=AT + timedelta(seconds=5)),
    )

    runtime = second.groups[0].decision.state.get(session.entries[0].identity)
    assert runtime is not None and runtime.occurrence is not None
    assert runtime.occurrence.occurrence_id == 'O1'
    assert second.groups[0].decision.occurrence_changes == ()


def test_error_on_open_occurrence_starts_technical_hold_without_normalizing() -> None:
    session = _session(engine_configuration())
    lifecycle, _ids = _lifecycle()
    first = lifecycle.run(
        previous=None,
        session=session,
        cycle=_cycle(session, AlarmStatus.ACTIVE, at=AT),
    )
    error_at = AT + timedelta(seconds=5)

    second = lifecycle.run(
        previous=first.state,
        session=session,
        cycle=_cycle(session, AlarmStatus.ERROR, at=error_at),
    )

    runtime = second.groups[0].decision.state.get(session.entries[0].identity)
    assert runtime is not None and runtime.occurrence is not None
    assert runtime.technical_hold is not None
    assert runtime.technical_hold.started_at == error_at
    assert runtime.technical_hold.due_at == error_at + timedelta(seconds=300)


def test_management_is_processed_in_same_cycle_and_uses_configured_reappearance() -> None:
    base = engine_configuration()
    configuration = _configuration_with_plan(
        base,
        replace(base.planned_alarms[0], reappearance_after_seconds=300),
    )
    session = _session(configuration)
    provider = InputsProvider()
    lifecycle, _ids = _lifecycle(provider)
    first = lifecycle.run(
        previous=None,
        session=session,
        cycle=_cycle(session, AlarmStatus.ACTIVE, at=AT),
    )
    identity = session.entries[0].identity
    provider.value = AlarmOperationalInputs(
        management_actions=(
            ManagementAction(
                input_id='management-1',
                alarm_identity=identity,
                source_occurrence_id='O1',
                tool_key='tool_a',
                actor_key='operator',
                source_created_at=AT + timedelta(seconds=5),
            ),
        )
    )
    managed_at = AT + timedelta(seconds=5)

    second = lifecycle.run(
        previous=first.state,
        session=session,
        cycle=_cycle(session, AlarmStatus.ACTIVE, at=managed_at),
    )

    decision = second.groups[0].decision
    assert decision.management_action_results[0].outcome is ManagementActionOutcome.EFFECTIVE
    runtime = decision.state.get(identity)
    assert runtime is not None and runtime.management_effect is not None
    assert runtime.management_effect.reappearance_due_at == managed_at + timedelta(seconds=300)
    assert provider.calls[-1] == (session, managed_at)


def test_disabling_alarm_reconciles_configuration_before_cycle() -> None:
    source_session = _session(engine_configuration())
    lifecycle, _ids = _lifecycle()
    first = lifecycle.run(
        previous=None,
        session=source_session,
        cycle=_cycle(source_session, AlarmStatus.ACTIVE, at=AT),
    )
    target_base = engine_configuration(release='ALARMS-8')
    identity = source_session.entries[0].identity
    target_configuration = EngineAlarmConfiguration(
        resolution_key=target_base.resolution_key,
        defined_alarm_identities=(identity,),
        planned_alarms=(),
        parameters_by_alarm={},
    )
    target_session = _session(target_configuration)
    cycle_at = AT + timedelta(seconds=5)

    result = lifecycle.run(
        previous=first.state,
        session=target_session,
        cycle=AlarmEvaluationCycleResult(cycle_at=cycle_at, evaluations=()),
    )

    group = result.groups[0]
    assert group.adoption_decision is not None
    closed = group.adoption_decision.occurrence_changes[0].occurrence
    assert closed.closure_reason is OccurrenceClosureReason.CONFIGURATION_DISABLED
    assert result.state.groups == ()


def test_structural_reset_closes_old_continuity_then_new_cycle_can_open_new_occurrence() -> None:
    source_session = _session(engine_configuration())
    lifecycle, _ids = _lifecycle()
    first = lifecycle.run(
        previous=None,
        session=source_session,
        cycle=_cycle(source_session, AlarmStatus.ACTIVE, at=AT),
    )
    target_base = engine_configuration(release='ALARMS-8')
    target_configuration = _configuration_with_plan(
        target_base,
        replace(target_base.planned_alarms[0], criticality=Criticality.C2),
    )
    target_session = _session(target_configuration)
    cycle_at = AT + timedelta(seconds=5)

    result = lifecycle.run(
        previous=first.state,
        session=target_session,
        cycle=_cycle(target_session, AlarmStatus.ACTIVE, at=cycle_at),
    )

    group = result.groups[0]
    assert group.adoption_decision is not None
    assert group.adoption_decision.occurrence_changes[0].occurrence.occurrence_id == 'O1'
    runtime = group.decision.state.get(target_session.entries[0].identity)
    assert runtime is not None and runtime.occurrence is not None
    assert runtime.occurrence.occurrence_id == 'O2'


def test_reappearance_delay_change_with_live_management_effect_is_blocked_explicitly() -> None:
    base = engine_configuration()
    source_configuration = _configuration_with_plan(
        base,
        replace(base.planned_alarms[0], reappearance_after_seconds=300),
    )
    source_session = _session(source_configuration)
    provider = InputsProvider()
    lifecycle, _ids = _lifecycle(provider)
    first = lifecycle.run(
        previous=None,
        session=source_session,
        cycle=_cycle(source_session, AlarmStatus.ACTIVE, at=AT),
    )
    identity = source_session.entries[0].identity
    managed_at = AT + timedelta(seconds=5)
    provider.value = AlarmOperationalInputs(
        management_actions=(
            ManagementAction(
                input_id='management-1',
                alarm_identity=identity,
                source_occurrence_id='O1',
                tool_key='tool_a',
                actor_key='operator',
                source_created_at=managed_at,
            ),
        )
    )
    managed = lifecycle.run(
        previous=first.state,
        session=source_session,
        cycle=_cycle(source_session, AlarmStatus.ACTIVE, at=managed_at),
    )
    target_base = engine_configuration(release='ALARMS-8')
    target_configuration = _configuration_with_plan(
        target_base,
        replace(target_base.planned_alarms[0], reappearance_after_seconds=600),
    )
    target_session = _session(target_configuration)
    provider.value = AlarmOperationalInputs()

    with pytest.raises(
        AlarmLifecycleOrchestrationError,
        match='reappearance deadline reconciliation is not implemented',
    ):
        lifecycle.run(
            previous=managed.state,
            session=target_session,
            cycle=_cycle(
                target_session,
                AlarmStatus.ACTIVE,
                at=managed_at + timedelta(seconds=5),
            ),
        )
