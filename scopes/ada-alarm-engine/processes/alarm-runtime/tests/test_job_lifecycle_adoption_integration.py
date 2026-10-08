from dataclasses import replace
from datetime import UTC, datetime, timedelta

from ada.alarms.core import (
    AlarmEvaluation,
    AlarmStatus,
    EvidenceSnapshot,
    ManagementAction,
    ManagementEffectChangeKind,
    OccurrenceClosureReason,
)
from ada.alarms.materialization import EngineAlarmConfiguration
from ada.processes.alarm_runtime import (
    AlarmEvaluationCycleResult,
    AlarmLifecycleCycle,
    AlarmOperationalInputs,
    AlarmRuntimeConfigurationOutcome,
    AlarmRuntimeJob,
    ConfigurationAdoptionDisposition,
)
from atlanticus.operational_data.sources import DataSourceApplications

from .support import engine_configuration, registry

AT = datetime(2026, 10, 7, 21, 0, tzinfo=UTC)


class Reader:
    def __init__(self, configurations):
        self.configurations = tuple(configurations)
        self.position = 0

    def read_published_engine(self, *, source_key):
        assert source_key == 'alarm-configuration'
        configuration = self.configurations[min(self.position, len(self.configurations) - 1)]
        self.position += 1
        return configuration


class ActiveCycle:
    def __init__(self, times):
        self.times = iter(times)

    def run(self, session):
        cycle_at = next(self.times)
        return AlarmEvaluationCycleResult(
            cycle_at=cycle_at,
            evaluations=tuple(
                AlarmEvaluation(
                    alarm_identity=entry.identity,
                    status=AlarmStatus.ACTIVE,
                    evaluated_at=cycle_at,
                    evidence_snapshot=EvidenceSnapshot(
                        contract_key='test',
                        contract_version='1',
                        payload={},
                    ),
                )
                for entry in session.entries
            ),
        )


class InputsProvider:
    def __init__(self):
        self.value = AlarmOperationalInputs()

    def read(self, *, session, cycle_at):
        return self.value


class Context:
    def __init__(self):
        self.memory = {}
        self.facts = {}
        self.work = False

    def raise_if_cancelled(self):
        return None

    def get_memory(self, key):
        return self.memory.get(key)

    def set_memory(self, key, value):
        self.memory[key] = value

    def set_iteration_fact(self, key, value):
        self.facts[key] = value

    def mark_iteration_work(self):
        self.work = True

    def set_next_iteration_delay(self, value):
        return None


def _job(configurations, *, times, provider=None):
    return AlarmRuntimeJob(
        reader=Reader(configurations),
        source_key='alarm-configuration',
        evaluator_registry=registry(),
        source_applications=DataSourceApplications(pi='pi-app'),
        cycle=ActiveCycle(times),
        lifecycle=AlarmLifecycleCycle(
            inputs_provider=InputsProvider() if provider is None else provider
        ),
    )


def _with_plan(configuration, updated_plan):
    return EngineAlarmConfiguration(
        resolution_key=configuration.resolution_key,
        defined_alarm_identities=configuration.defined_alarm_identities,
        planned_alarms=(updated_plan,),
        parameters_by_alarm=configuration.parameters_by_alarm,
    )


def _current(result, identity):
    assert result.lifecycle is not None
    group = result.lifecycle.state.group_for('mill_feed')
    assert group is not None
    runtime = group.get(identity)
    assert runtime is not None and runtime.occurrence is not None
    return group, runtime


def test_job_preserves_active_occurrence_across_compatible_adoption_and_unchanged_cycle():
    source = engine_configuration()
    target = engine_configuration(release='ALARMS-8', limit=12.0)
    job = _job(
        (source, target, target),
        times=(AT, AT + timedelta(seconds=5), AT + timedelta(seconds=10)),
    )
    context = Context()
    identity = source.planned_alarms[0].identity

    first = job.run_iteration(context)
    source_group, source_runtime = _current(first, identity)
    second = job.run_iteration(context)
    target_group, target_runtime = _current(second, identity)
    third = job.run_iteration(context)
    final_group, final_runtime = _current(third, identity)

    assert first.outcome is AlarmRuntimeConfigurationOutcome.BOOTSTRAPPED
    assert second.outcome is AlarmRuntimeConfigurationOutcome.ADOPTED
    assert third.outcome is AlarmRuntimeConfigurationOutcome.UNCHANGED
    assert second.lifecycle is not None
    assert second.lifecycle.adoption_plan is not None
    assert second.lifecycle.adoption_plan.changes[0].disposition is (
        ConfigurationAdoptionDisposition.COMPATIBLE
    )
    assert target_group.episode is not None and source_group.episode is not None
    assert final_group.episode is not None
    assert target_group.episode.episode_id == source_group.episode.episode_id
    assert final_group.episode.episode_id == source_group.episode.episode_id
    assert target_runtime.occurrence.occurrence_id == source_runtime.occurrence.occurrence_id
    assert final_runtime.occurrence.occurrence_id == source_runtime.occurrence.occurrence_id
    assert second.lifecycle.groups[0].adoption_decision is not None
    assert second.lifecycle.groups[0].adoption_decision.occurrence_changes == ()
    assert second.lifecycle.groups[0].adoption_decision.episode_changes == ()
    assert third.lifecycle is not None and third.lifecycle.adoption_plan is None
    assert third.lifecycle.state.configuration == target


def test_job_rejects_group_mutation_without_changing_pinned_lifecycle():
    source = engine_configuration()
    target_base = engine_configuration(release='ALARMS-8')
    target = _with_plan(
        target_base,
        replace(target_base.planned_alarms[0], priority_group='other_group'),
    )
    job = _job(
        (source, target, source),
        times=(AT, AT + timedelta(seconds=5), AT + timedelta(seconds=10)),
    )
    context = Context()
    identity = source.planned_alarms[0].identity

    first = job.run_iteration(context)
    _, original = _current(first, identity)
    rejected = job.run_iteration(context)
    _, after_rejection = _current(rejected, identity)
    resumed = job.run_iteration(context)
    _, after_resume = _current(resumed, identity)

    assert rejected.outcome is AlarmRuntimeConfigurationOutcome.REJECTED
    assert rejected.reason == 'published_engine_not_adoptable'
    assert rejected.session is first.session
    assert rejected.lifecycle is not None and rejected.lifecycle.adoption_plan is None
    assert after_rejection.occurrence.occurrence_id == original.occurrence.occurrence_id
    assert resumed.outcome is AlarmRuntimeConfigurationOutcome.UNCHANGED
    assert resumed.session is first.session
    assert after_resume.occurrence.occurrence_id == original.occurrence.occurrence_id
    assert resumed.lifecycle is not None and resumed.lifecycle.state.configuration == source


def test_job_closes_active_occurrence_when_configuration_disables_alarm():
    source = engine_configuration()
    target_base = engine_configuration(release='ALARMS-8')
    target = EngineAlarmConfiguration(
        resolution_key=target_base.resolution_key,
        defined_alarm_identities=target_base.defined_alarm_identities,
        planned_alarms=(),
        parameters_by_alarm={},
    )
    job = _job((source, target), times=(AT, AT + timedelta(seconds=5)))
    context = Context()

    first = job.run_iteration(context)
    assert first.lifecycle is not None and first.lifecycle.state.groups
    adopted = job.run_iteration(context)

    assert adopted.outcome is AlarmRuntimeConfigurationOutcome.ADOPTED
    assert adopted.lifecycle is not None
    assert adopted.lifecycle.state.configuration == target
    assert adopted.lifecycle.state.groups == ()
    assert adopted.lifecycle.adoption_plan is not None
    assert adopted.lifecycle.adoption_plan.changes[0].disposition is (
        ConfigurationAdoptionDisposition.DISABLED
    )
    group = adopted.lifecycle.groups[0]
    assert group.adoption_decision is not None
    assert len(group.adoption_decision.occurrence_changes) == 1
    assert group.adoption_decision.occurrence_changes[0].occurrence.closure_reason is (
        OccurrenceClosureReason.CONFIGURATION_DISABLED
    )
    assert len(group.adoption_decision.episode_changes) == 1


def test_job_recalculates_management_deadline_during_compatible_adoption():
    base = engine_configuration()
    source = _with_plan(
        base,
        replace(base.planned_alarms[0], reappearance_after_seconds=300),
    )
    target_base = engine_configuration(release='ALARMS-8')
    target = _with_plan(
        target_base,
        replace(target_base.planned_alarms[0], reappearance_after_seconds=600),
    )
    provider = InputsProvider()
    managed_at = AT + timedelta(seconds=5)
    job = _job(
        (source, source, target),
        times=(AT, managed_at, AT + timedelta(seconds=10)),
        provider=provider,
    )
    context = Context()
    identity = source.planned_alarms[0].identity

    first = job.run_iteration(context)
    _, current = _current(first, identity)
    provider.value = AlarmOperationalInputs(
        management_actions=(
            ManagementAction(
                input_id='management-1',
                alarm_identity=identity,
                source_occurrence_id=current.occurrence.occurrence_id,
                tool_key='tool_a',
                actor_key='operator',
                source_created_at=managed_at,
            ),
        )
    )
    managed = job.run_iteration(context)
    _, managed_runtime = _current(managed, identity)
    assert managed_runtime.management_effect is not None
    assert managed_runtime.management_effect.reappearance_due_at == managed_at + timedelta(
        seconds=300
    )
    provider.value = AlarmOperationalInputs()

    adopted = job.run_iteration(context)
    _, adopted_runtime = _current(adopted, identity)
    assert adopted.outcome is AlarmRuntimeConfigurationOutcome.ADOPTED
    assert adopted_runtime.occurrence.occurrence_id == current.occurrence.occurrence_id
    assert adopted_runtime.management_effect is not None
    assert (
        adopted_runtime.management_effect.effect_id == managed_runtime.management_effect.effect_id
    )
    assert adopted_runtime.management_effect.reappearance_due_at == managed_at + timedelta(
        seconds=600
    )
    assert adopted.lifecycle is not None
    group = adopted.lifecycle.groups[0]
    assert group.adoption_decision is not None
    assert any(
        change.kind is ManagementEffectChangeKind.UPDATED
        for change in group.adoption_decision.management_effect_changes
    )
