from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

import pytest

from ada.alarms.core import (
    AlarmEvaluation,
    AlarmStatus,
    EvaluationError,
    EvaluationErrorOrigin,
    EvidenceSnapshot,
    GroupLifecycleState,
    reduce_group_cycle,
    reduce_initial_technical_incidents,
)
from ada.alarms.persistence.operational import AlarmArtifactRefSnapshot
from ada.processes.alarm_runtime.cycle import AlarmEvaluationCycleResult
from ada.processes.alarm_runtime.durable_commit import (
    AlarmDurableCycleCommitter,
    AlarmRuntimeDurabilityError,
)
from ada.processes.alarm_runtime.durable_recovery import RecoveredAlarmAuthority
from ada.processes.alarm_runtime.lifecycle import (
    AlarmLifecycleCycleResult,
    AlarmLifecycleGroupResult,
    AlarmLifecycleRuntimeState,
    AlarmOperationalInputs,
)

from .support import engine_configuration

NOW = datetime(2026, 10, 8, 10, 0, tzinfo=UTC)


class Context:
    def __init__(self):
        self.checks = 0
        self.fenced = 0
        self.revoked = False

    def assert_lease_current(self):
        self.checks += 1
        if self.revoked:
            raise RuntimeError('lease lost')

    def fenced_mutation(self):
        self.fenced += 1
        return nullcontext()


class Store:
    def __init__(self, context):
        self.context = context
        self.snapshots = {}
        self.committed = []
        self.raise_on_commit = False
        self.revoke_after_commit = False

    def read_snapshot(self, priority_group):
        return self.snapshots.get(priority_group)

    def commit_batch(self, records, *, assert_authority, fenced_mutation):
        assert_authority()
        with fenced_mutation():
            assert_authority()
            if self.raise_on_commit:
                raise OSError('forced WAL error')
            self.committed.append(tuple(records))
            for record in records:
                self.snapshots[record.commit.priority_group] = record.snapshot_after
            if self.revoke_after_commit:
                self.context.revoked = True


def _ref():
    return AlarmArtifactRefSnapshot(
        source_key='alarm-configuration',
        result_id='alarm-materialization-' + 'a' * 64,
        manifest_sha256='b' * 64,
        alarm_configuration_revision='ALARMS-7',
        confirmed_tool_catalog_revision='TOOLS-4',
    )


def _evaluation(at, *, key=None, active=False):
    configuration = engine_configuration()
    if key is not None:
        return AlarmEvaluation(
            alarm_identity=configuration.planned_alarms[0].identity,
            status=AlarmStatus.ERROR,
            evaluated_at=at,
            error=EvaluationError(
                origin=EvaluationErrorOrigin.QUALITY,
                error_key=key,
                message='Quality failed',
            ),
        )
    return AlarmEvaluation(
        alarm_identity=configuration.planned_alarms[0].identity,
        status=AlarmStatus.ACTIVE if active else AlarmStatus.INACTIVE,
        evaluated_at=at,
        evidence_snapshot=EvidenceSnapshot(contract_key='test', contract_version='1', payload={}),
    )


def _cycle(previous, *, at, key=None, active=False):
    evaluation = _evaluation(at, key=key, active=active)
    group_name = previous.configuration.planned_alarms[0].priority_group
    old = previous.group_for(group_name) or GroupLifecycleState(priority_group=group_name)
    decision = reduce_group_cycle(
        old,
        cycle_at=at,
        planned_alarms=previous.configuration.planned_alarms,
        evaluations=(evaluation,),
        occurrence_id_factory=lambda _identity, _at: 'occurrence-1',
        episode_id_factory=lambda _group, _at: 'episode-1',
    )
    incidents = reduce_initial_technical_incidents(
        previous.technical_incidents,
        evaluations=(evaluation,),
        executable_groups={evaluation.alarm_identity: group_name},
        physical_occurrences=frozenset(
            alarm.alarm_identity for alarm in decision.state.alarms if alarm.occurrence is not None
        ),
        cycle_at=at,
    )
    result = AlarmLifecycleCycleResult(
        cycle_at=at,
        inputs=AlarmOperationalInputs(),
        groups=(AlarmLifecycleGroupResult(group_name, None, decision),),
        state=AlarmLifecycleRuntimeState(
            configuration=previous.configuration,
            groups=(decision.state,),
            technical_incidents=incidents.open_incidents,
        ),
        technical_incident_changes=incidents.changes,
    )
    return AlarmEvaluationCycleResult(at, (evaluation,)), result


def _execute(previous, store, context, *, at=NOW, key=None, active=False):
    cycle, lifecycle = _cycle(previous, at=at, key=key, active=active)
    return AlarmDurableCycleCommitter(persistence=store).commit(
        context,
        recovered=RecoveredAlarmAuthority(artifact_ref=_ref(), lifecycle=previous),
        previous=previous,
        cycle=cycle,
        lifecycle=lifecycle,
    )


def _initial():
    return AlarmLifecycleRuntimeState(configuration=engine_configuration())


def test_initial_technical_error_commits_then_recovers_same_incident():
    context = Context()
    store = Store(context)
    state = _execute(_initial(), store, context, key='A')
    assert len(store.committed) == 1
    assert len(state.technical_incidents) == 1
    assert store.snapshots['mill_feed'].as_document()['technical_incidents']
    assert context.fenced == 1


def test_repeated_technical_error_does_not_append_batch():
    context = Context()
    store = Store(context)
    state = _execute(_initial(), store, context, key='A')
    first_id = state.technical_incidents[0].incident_id
    for n in range(1, 101):
        state = _execute(state, store, context, at=NOW + timedelta(seconds=n * 3), key='A')
    assert len(store.committed) == 1
    assert state.technical_incidents[0].incident_id == first_id


def test_error_change_and_resolution_are_committed_once_each():
    context = Context()
    store = Store(context)
    state = _execute(_initial(), store, context, key='A')
    state = _execute(state, store, context, at=NOW + timedelta(seconds=3), key='B')
    state = _execute(state, store, context, at=NOW + timedelta(seconds=6))
    assert len(store.committed) == 3
    kinds = [entry[0].records['technical_incident_changes'][0]['kind'] for entry in store.committed]
    assert kinds == ['STARTED', 'CHANGED', 'RESOLVED']
    assert state.technical_incidents == ()


def test_physical_alarm_persists_evidence_due_before_returning_state():
    context = Context()
    store = Store(context)
    state = _execute(_initial(), store, context, active=True)
    assert len(store.committed) == 1
    assert len(store.committed[0][0].records['evidence_records']) == 1
    assert state.groups[0].alarms[0].next_evidence_due_at == NOW + timedelta(minutes=5)


def test_failed_wal_write_never_returns_unconfirmed_memory():
    context = Context()
    store = Store(context)
    store.raise_on_commit = True
    state = _initial()
    with pytest.raises(OSError, match='forced WAL'):
        _execute(state, store, context, key='A')
    assert store.snapshots == {}
    assert store.committed == []
    assert state.technical_incidents == ()


def test_lost_lease_before_commit_does_not_write():
    context = Context()
    store = Store(context)
    context.revoked = True
    with pytest.raises(RuntimeError, match='lease lost'):
        _execute(_initial(), store, context, key='A')
    assert store.committed == []


def test_lost_lease_after_durable_write_requires_recovery():
    context = Context()
    store = Store(context)
    store.revoke_after_commit = True
    state = _initial()
    with pytest.raises(RuntimeError, match='lease lost'):
        _execute(state, store, context, key='A')
    assert len(store.committed) == 1
    assert state.technical_incidents == ()


def test_rejects_configuration_divergence_without_writing():
    context = Context()
    store = Store(context)
    state = AlarmLifecycleRuntimeState(configuration=engine_configuration(release='OTHER'))
    cycle, lifecycle = _cycle(state, at=NOW, key='A')
    with pytest.raises(AlarmRuntimeDurabilityError, match='EFFECTIVE revisions'):
        AlarmDurableCycleCommitter(persistence=store).commit(
            context,
            recovered=RecoveredAlarmAuthority(artifact_ref=_ref(), lifecycle=state),
            previous=state,
            cycle=cycle,
            lifecycle=lifecycle,
        )
    assert store.committed == []


class RuntimeContext(Context):
    def __init__(self):
        super().__init__()
        self.memory = {}
        self.facts = {}
        self.delay = None

    def get_memory(self, key):
        return self.memory.get(key)

    def set_memory(self, key, value):
        self.memory[key] = value

    def set_iteration_fact(self, key, value):
        self.facts[key] = value

    def set_next_iteration_delay(self, seconds):
        self.delay = seconds

    def mark_iteration_work(self):
        return None

    def raise_if_cancelled(self):
        return None


class PublishedReader:
    def __init__(self, configurations):
        self.configurations = list(configurations)
        self.calls = 0

    def read_published_engine(self, *, source_key):
        assert source_key == 'alarm-configuration'
        configuration = self.configurations[min(self.calls, len(self.configurations) - 1)]
        self.calls += 1
        return configuration


class ErrorCycle:
    def __init__(self):
        self.calls = 0

    def run(self, session):
        at = NOW + timedelta(seconds=self.calls * 3)
        self.calls += 1
        return AlarmEvaluationCycleResult(
            cycle_at=at,
            evaluations=(_evaluation(at, key='A'),),
        )


def _durable_job(*, effective):
    from types import SimpleNamespace

    from ada.processes.alarm_runtime.durable_recovery import AlarmDurableRecovery
    from ada.processes.alarm_runtime.job import AlarmRuntimeJob
    from atlanticus.operational_data.sources import DataSourceApplications

    from .support import registry
    from .test_durable_recovery import ReadyReader, Store as RecoveryStore

    configuration = engine_configuration()
    recovered_store = RecoveryStore(
        effective=SimpleNamespace(target_artifact_ref=_ref()) if effective else None,
        durable=effective,
    )
    context = RuntimeContext()
    writer_store = Store(context)
    job = AlarmRuntimeJob(
        reader=PublishedReader((configuration, engine_configuration(release='ALARMS-8'))),
        source_key='alarm-configuration',
        evaluator_registry=registry(),
        source_applications=DataSourceApplications(pi='pi-app'),
        cycle=ErrorCycle(),
        durable_recovery=AlarmDurableRecovery(
            persistence=recovered_store,
            materializations=ReadyReader(configuration),
            source_key='alarm-configuration',
        ),
        durable_committer=AlarmDurableCycleCommitter(persistence=writer_store),
    )
    return context, job, writer_store


def test_job_must_recover_before_durable_iteration():
    from ada.processes.alarm_runtime.errors import AlarmRuntimeConfigurationError

    context, job, store = _durable_job(effective=True)
    with pytest.raises(AlarmRuntimeConfigurationError, match='recovery must run'):
        job.run_iteration(context)
    assert store.committed == []


def test_job_recovers_then_commits_before_publishing_lifecycle_memory():
    context, job, store = _durable_job(effective=True)
    job.recover(context)
    result = job.run_iteration(context)
    assert len(store.committed) == 1
    assert len(result.lifecycle.state.technical_incidents) == 1
    assert len(context.memory['ada.alarm_engine.runtime.lifecycle_state'].technical_incidents) == 1
    assert context.checks >= 4


def test_job_requires_durable_adoption_before_switching_configuration():
    from ada.processes.alarm_runtime.job import AlarmRuntimeConfigurationOutcome

    context, job, store = _durable_job(effective=True)
    job.recover(context)
    job.run_iteration(context)
    result = job.run_iteration(context)
    assert result.outcome is AlarmRuntimeConfigurationOutcome.REJECTED
    assert result.reason == 'published_engine_pending_durable_adoption'
    assert result.lifecycle.state.configuration == engine_configuration()
    assert len(store.committed) == 1


def test_runtime_waits_when_no_effective_artifact_is_durable():
    from ada.processes.alarm_runtime.job import AlarmRuntimeConfigurationOutcome

    context, job, store = _durable_job(effective=False)
    job.recover(context)
    result = job.run_iteration(context)
    assert result.outcome is AlarmRuntimeConfigurationOutcome.WAITING
    assert result.reason == 'effective_configuration_missing'
    assert result.cycle is None
    assert store.committed == []
