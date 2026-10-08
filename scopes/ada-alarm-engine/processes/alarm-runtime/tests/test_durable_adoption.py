from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from ada.alarms.core import (
    AlarmEpisode,
    AlarmOccurrence,
    AlarmRuntimeState,
    AlarmStatus,
    GroupLifecycleState,
    RuntimeEvaluationState,
)
from ada.alarms.materialization import AlarmResolutionStatus, EngineAlarmConfiguration
from ada.alarms.persistence.operational import (
    AlarmPersistence,
    ConfigurationAdoptionRecord,
    ConfigurationAdoptionRecordV2,
    EngineCommitMetadata,
    EngineCommitRecord,
)
from ada.alarms.persistence.operational.lifecycle_snapshot import snapshot_group_lifecycle
from ada.contracts.alarms import AlarmIdentity
from ada.processes.alarm_runtime import AlarmRuntimeConfigurationOutcome, AlarmRuntimeJob
from ada.processes.alarm_runtime.durable_adoption import (
    AlarmDurableAdopter,
    AlarmOperationalAdoptionRequired,
)
from ada.processes.alarm_runtime.durable_commit import AlarmDurableCycleCommitter
from ada.processes.alarm_runtime.durable_recovery import (
    AlarmDurableRecovery,
    RecoveredAlarmAuthority,
)
from atlanticus.operational_data.sources import DataSourceApplications

from .support import engine_configuration, registry

AT = datetime(2026, 10, 8, 15, 0, tzinfo=UTC)
IDENTITY = AlarmIdentity('mill', 'risk')


class Context:
    def __init__(self):
        self.memory = {}
        self.events = []
        self.revoked = False

    def assert_lease_current(self):
        self.events.append('authority')
        if self.revoked:
            raise RuntimeError('lease lost')

    def fenced_mutation(self):
        self.events.append('fence')
        return nullcontext()

    def raise_if_cancelled(self):
        return None

    def get_memory(self, key):
        return self.memory.get(key)

    def set_memory(self, key, value):
        self.events.append('memory')
        self.memory[key] = value

    def set_next_iteration_delay(self, value):
        self.events.append('delay')

    def set_iteration_fact(self, key, value):
        return None

    def mark_iteration_work(self):
        self.events.append('work')


class Materializations:
    def __init__(self, *values):
        self.versions = {item.result_id: item for item in values}
        self.published = None if not values else values[-1]
        self.ready_reads = []

    def read_published_ready(self, *, source_key):
        assert source_key == 'alarm-configuration'
        return self.published

    def read_ready(self, *, source_key, result_id, expected_manifest_sha256=None):
        assert source_key == 'alarm-configuration'
        ready = self.versions[result_id]
        assert ready.manifest_sha256 == expected_manifest_sha256
        self.ready_reads.append(result_id)
        return ready


def _ready(letter='a', *, release='ALARMS-7', configuration=None):
    configuration = (
        engine_configuration(release=release) if configuration is None else configuration
    )
    result_id = 'alarm-materialization-' + letter * 64
    return SimpleNamespace(
        result_id=result_id,
        manifest_sha256=letter * 64,
        manifest=SimpleNamespace(
            source_key='alarm-configuration',
            result_id=result_id,
            status=AlarmResolutionStatus.READY,
            resolution_key=configuration.resolution_key,
        ),
        engine=configuration,
    )


def _adopter(store, versions, *, at=AT):
    return AlarmDurableAdopter(
        persistence=store,
        materializations=versions,
        source_key='alarm-configuration',
        clock=lambda: at,
    )


def _recovery(store, versions):
    return AlarmDurableRecovery(
        persistence=store,
        materializations=versions,
        source_key='alarm-configuration',
    )


def _bootstrap(store, versions, context):
    recovered = _recovery(store, versions).recover(context)
    adopter = _adopter(store, versions)
    selected = adopter.read_candidate()
    adopter.adopt(context, recovered=recovered, ready=selected)
    return _recovery(store, versions).recover(context)


def _empty_or_active_state(*, active=False):
    if not active:
        return GroupLifecycleState(priority_group='mill_feed')
    occurrence = AlarmOccurrence(
        occurrence_id='O1',
        alarm_identity=IDENTITY,
        episode_id='E1',
        started_at=AT,
        alarm_configuration_revision='ALARMS-7',
        tool_registry_revision='TOOLS-4',
    )
    alarm = AlarmRuntimeState(
        alarm_identity=IDENTITY,
        occurrence=occurrence,
        last_evaluation=RuntimeEvaluationState(status=AlarmStatus.ACTIVE, evaluated_at=AT),
        management_cycle=1,
    )
    return GroupLifecycleState(
        priority_group='mill_feed',
        episode=AlarmEpisode(episode_id='E1', priority_group='mill_feed', started_at=AT),
        alarms=(alarm,),
    )


def _insert_snapshot(store, *, active=False):
    state = _empty_or_active_state(active=active)
    at = AT + timedelta(seconds=1)
    snapshot = snapshot_group_lifecycle(
        state,
        commit_id='BASE',
        alarm_configuration_revision='ALARMS-7',
        tool_registry_revision='TOOLS-4',
        technical_incidents=(),
    )
    record = EngineCommitRecord.create(
        commit=EngineCommitMetadata(
            commit_id='BASE',
            cycle_id='BASE',
            priority_group='mill_feed',
            previous_commit_id=None,
            evaluated_at=at.isoformat().replace('+00:00', 'Z'),
            committed_at=at.isoformat().replace('+00:00', 'Z'),
            alarm_configuration_revision='ALARMS-7',
            tool_registry_revision='TOOLS-4',
            runtime_artifact_version='runtime/1',
            affected_alarms=(IDENTITY.canonical_key,),
        ),
        snapshot_after=snapshot,
    )
    store.commit_batch(
        (record,),
        assert_authority=lambda: None,
        fenced_mutation=lambda: nullcontext(),
    )


def _job(store, versions, cycle):
    adopter = _adopter(store, versions, at=AT + timedelta(seconds=3))
    return AlarmRuntimeJob(
        reader=SimpleNamespace(read_published_engine=lambda **kwargs: None),
        source_key='alarm-configuration',
        evaluator_registry=registry(),
        source_applications=DataSourceApplications(pi='pi-app'),
        cycle=cycle,
        durable_recovery=_recovery(store, versions),
        durable_committer=AlarmDurableCycleCommitter(persistence=store),
        durable_adopter=adopter,
    )


class NoCycle:
    def __init__(self):
        self.calls = 0

    def run(self, session):
        self.calls += 1
        raise AssertionError('adoption must not evaluate before durable confirmation')


def test_initial_bootstrap_creates_v1_adoption_before_any_group(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    versions = Materializations(_ready())
    context = Context()
    recovered = _bootstrap(store, versions, context)
    adoptions = store.read_durable_adoptions()
    assert len(adoptions) == 1
    assert type(adoptions[0].record) is ConfigurationAdoptionRecord
    assert recovered.artifact_ref.result_id == versions.published.result_id
    assert recovered.lifecycle.configuration == versions.published.engine
    assert store.list_snapshots() == ()
    assert 'fence' in context.events


def test_v2_rebases_empty_snapshot_without_physical_events(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    first, second = _ready(), _ready('b', release='ALARMS-8')
    versions = Materializations(first)
    context = Context()
    _bootstrap(store, versions, context)
    _insert_snapshot(store)
    previous = _recovery(store, versions).recover(context)
    versions.versions[second.result_id] = second
    versions.published = second
    adopter = _adopter(store, versions, at=AT + timedelta(seconds=3))
    adopted = adopter.adopt(context, recovered=previous, ready=second)
    assert adopted.result_id == second.result_id
    records = store.read_durable_adoptions()
    assert isinstance(records[-1].record, ConfigurationAdoptionRecordV2)
    engine = store.read_durable_records()[-1].record
    assert set(engine.records) == {'configuration_rebases'}
    assert engine.commit.affected_alarms == ()
    assert _recovery(store, versions).recover(context).lifecycle.configuration == second.engine


def test_withdrawal_with_open_occurrence_is_not_silently_rebased(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    first = _ready()
    versions = Materializations(first)
    context = Context()
    _bootstrap(store, versions, context)
    _insert_snapshot(store, active=True)
    previous = _recovery(store, versions).recover(context)
    revised = engine_configuration(release='ALARMS-8')
    disabled = EngineAlarmConfiguration(
        resolution_key=revised.resolution_key,
        defined_alarm_identities=revised.defined_alarm_identities,
        planned_alarms=(),
        parameters_by_alarm={},
    )
    second = _ready('b', release='ALARMS-8', configuration=disabled)
    with pytest.raises(AlarmOperationalAdoptionRequired, match='operational lifecycle'):
        _adopter(store, versions, at=AT + timedelta(seconds=3)).adopt(
            context, recovered=previous, ready=second
        )
    assert store.read_effective_head().target_artifact_ref == previous.artifact_ref
    assert len(store.read_durable_adoptions()) == 1


def test_lost_lease_before_adoption_does_not_write(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    versions = Materializations(_ready())
    context = Context()
    context.revoked = True
    with pytest.raises(RuntimeError, match='lease lost'):
        _adopter(store, versions).adopt(
            context,
            recovered=RecoveredAlarmAuthority(artifact_ref=None, lifecycle=None),
            ready=versions.published,
        )
    assert store.read_head().durable is None


def test_ready_reference_requires_manifest_integrity(tmp_path):
    versions = Materializations(_ready())
    adopter = _adopter(AlarmPersistence(application_root=tmp_path), versions)
    versions.published.manifest.result_id = 'wrong'
    with pytest.raises(ValueError, match='identity'):
        adopter.reference_for(versions.published)


def test_job_bootstrap_is_durable_before_memory_or_cycle(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    versions = Materializations(_ready())
    cycle = NoCycle()
    job = _job(store, versions, cycle)
    context = Context()
    job.recover(context)
    memory_before = len([event for event in context.events if event == 'memory'])
    result = job.run_iteration(context)
    assert result.outcome is AlarmRuntimeConfigurationOutcome.BOOTSTRAPPED
    assert result.cycle is None
    assert cycle.calls == 0
    assert len(store.read_durable_adoptions()) == 1
    assert len([event for event in context.events if event == 'memory']) > memory_before
    assert context.events.index('fence') < context.events.index('work')


def test_job_waits_without_ready_and_effective(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    versions = Materializations()
    job = _job(store, versions, NoCycle())
    context = Context()
    job.recover(context)
    result = job.run_iteration(context)
    assert result.outcome is AlarmRuntimeConfigurationOutcome.WAITING
    assert store.read_head().durable is None


def test_job_rejects_unexecutable_bootstrap_without_adoption(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    versions = Materializations(_ready(configuration=engine_configuration(evaluator_key='missing')))
    job = _job(store, versions, NoCycle())
    context = Context()
    job.recover(context)
    result = job.run_iteration(context)
    assert result.outcome is AlarmRuntimeConfigurationOutcome.REJECTED
    assert result.reason == 'published_engine_not_executable'
    assert store.read_head().durable is None


def test_incompatible_new_ready_keeps_existing_effective(tmp_path):
    from dataclasses import replace

    from ada.alarms.core import AlarmEvaluation, EvidenceSnapshot
    from ada.processes.alarm_runtime.cycle import AlarmEvaluationCycleResult

    class InactiveCycle:
        def run(self, session):
            at = AT + timedelta(seconds=5)
            return AlarmEvaluationCycleResult(
                cycle_at=at,
                evaluations=tuple(
                    AlarmEvaluation(
                        alarm_identity=entry.identity,
                        status=AlarmStatus.INACTIVE,
                        evaluated_at=at,
                        evidence_snapshot=EvidenceSnapshot(
                            contract_key='test', contract_version='1', payload={}
                        ),
                    )
                    for entry in session.entries
                ),
            )

    store = AlarmPersistence(application_root=tmp_path)
    first = _ready()
    versions = Materializations(first)
    context = Context()
    job = _job(store, versions, InactiveCycle())
    job.recover(context)
    job.run_iteration(context)

    updated = engine_configuration(release='ALARMS-8')
    changed = replace(updated.planned_alarms[0], priority_group='new_group')
    incompatible = EngineAlarmConfiguration(
        resolution_key=updated.resolution_key,
        defined_alarm_identities=updated.defined_alarm_identities,
        planned_alarms=(changed,),
        parameters_by_alarm=updated.parameters_by_alarm,
    )
    versions.published = _ready('b', release='ALARMS-8', configuration=incompatible)
    result = job.run_iteration(context)
    assert result.outcome is AlarmRuntimeConfigurationOutcome.REJECTED
    assert result.reason == 'published_engine_not_adoptable'
    assert len(store.read_durable_adoptions()) == 1
    assert store.read_effective_head().target_artifact_ref.result_id == first.result_id


def test_crash_after_confirmed_wal_before_memory_is_recovered(tmp_path):
    class CrashAfterDurable(AlarmPersistence):
        def commit_adoption(
            self,
            record,
            *,
            group_records=(),
            assert_authority,
            fenced_mutation,
        ):
            super().commit_adoption(
                record,
                group_records=group_records,
                assert_authority=assert_authority,
                fenced_mutation=fenced_mutation,
            )
            raise RuntimeError('crash after durable adoption')

    store = CrashAfterDurable(application_root=tmp_path)
    versions = Materializations(_ready())
    context = Context()
    job = _job(store, versions, NoCycle())
    job.recover(context)
    with pytest.raises(RuntimeError, match='crash after durable adoption'):
        job.run_iteration(context)
    assert not any('execution_session' in key for key in context.memory)
    assert store.read_effective_head().target_artifact_ref.result_id == versions.published.result_id
    recovered = _recovery(store, versions).recover(Context())
    assert recovered.lifecycle.configuration == versions.published.engine
    assert len(store.read_durable_adoptions()) == 1


def test_repeated_exact_ready_does_not_adopt_twice(tmp_path):
    from ada.alarms.core import AlarmEvaluation, EvidenceSnapshot
    from ada.processes.alarm_runtime.cycle import AlarmEvaluationCycleResult

    class IdleCycle:
        def run(self, session):
            at = AT + timedelta(seconds=8)
            return AlarmEvaluationCycleResult(
                cycle_at=at,
                evaluations=tuple(
                    AlarmEvaluation(
                        alarm_identity=entry.identity,
                        status=AlarmStatus.INACTIVE,
                        evaluated_at=at,
                        evidence_snapshot=EvidenceSnapshot(
                            contract_key='test', contract_version='1', payload={}
                        ),
                    )
                    for entry in session.entries
                ),
            )

    store = AlarmPersistence(application_root=tmp_path)
    versions = Materializations(_ready())
    job = _job(store, versions, IdleCycle())
    context = Context()
    job.recover(context)
    initial = job.run_iteration(context)
    repeated = job.run_iteration(context)
    assert initial.outcome is AlarmRuntimeConfigurationOutcome.BOOTSTRAPPED
    assert repeated.outcome is AlarmRuntimeConfigurationOutcome.UNCHANGED
    assert len(store.read_durable_adoptions()) == 1
