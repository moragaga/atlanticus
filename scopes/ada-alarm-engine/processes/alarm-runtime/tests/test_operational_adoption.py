from __future__ import annotations

from contextlib import nullcontext
from datetime import timedelta

import pytest

from ada.alarms.core import (
    AlarmEvaluation,
    AlarmStatus,
    EvaluationError,
    EvaluationErrorOrigin,
    EvidenceSnapshot,
    GroupLifecycleState,
    reduce_initial_technical_incidents,
)
from ada.alarms.materialization import EngineAlarmConfiguration
from ada.alarms.persistence.operational import (
    AlarmPersistence,
    ConfigurationAdoptionRecordV2,
    EngineCommitMetadata,
    EngineCommitRecord,
)
from ada.alarms.persistence.operational.lifecycle_snapshot import (
    restore_group_lifecycle,
    snapshot_group_lifecycle,
)
from ada.contracts.alarms import AlarmIdentity
from ada.processes.alarm_runtime import AlarmRuntimeConfigurationOutcome
from ada.processes.alarm_runtime.adoption import plan_configuration_adoption
from ada.processes.alarm_runtime.cycle import AlarmEvaluationCycleResult
from ada.processes.alarm_runtime.operational_adoption import prepare_operational_adoption

from .support import engine_configuration
from .test_durable_adoption import (
    AT,
    Context,
    Materializations,
    _adopter,
    _bootstrap,
    _insert_snapshot,
    _job,
    _ready,
    _recovery,
)


def _disabled_ready():
    configuration = engine_configuration(release='ALARMS-8')
    disabled = EngineAlarmConfiguration(
        resolution_key=configuration.resolution_key,
        defined_alarm_identities=configuration.defined_alarm_identities,
        planned_alarms=(),
        parameters_by_alarm={},
    )
    return _ready('b', release='ALARMS-8', configuration=disabled)


def _additional_snapshot(store, *, group, incidents=()):
    state = GroupLifecycleState(priority_group=group)
    snapshot = snapshot_group_lifecycle(
        state,
        commit_id='BASE-' + group,
        alarm_configuration_revision='ALARMS-7',
        tool_registry_revision='TOOLS-4',
        technical_incidents=incidents,
    )
    at = AT + timedelta(seconds=1)
    record = EngineCommitRecord.create(
        commit=EngineCommitMetadata(
            commit_id=snapshot.last_commit_id,
            cycle_id='BASE',
            priority_group=group,
            previous_commit_id=None,
            evaluated_at=at.isoformat().replace('+00:00', 'Z'),
            committed_at=at.isoformat().replace('+00:00', 'Z'),
            alarm_configuration_revision='ALARMS-7',
            tool_registry_revision='TOOLS-4',
            runtime_artifact_version='runtime/1',
            affected_alarms=(
                tuple(incident.alarm_identity.canonical_key for incident in incidents)
                or (AlarmIdentity('fixture', group).canonical_key,)
            ),
        ),
        snapshot_after=snapshot,
    )
    store.commit_batch(
        (record,), assert_authority=lambda: None, fenced_mutation=lambda: nullcontext()
    )
    return snapshot


def test_open_occurrence_closes_with_real_records_in_v2_adoption(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    first, second = _ready(), _disabled_ready()
    versions = Materializations(first)
    context = Context()
    _bootstrap(store, versions, context)
    _insert_snapshot(store, active=True)
    recovered = _recovery(store, versions).recover(context)
    versions.versions[second.result_id] = second
    versions.published = second
    _adopter(store, versions, at=AT + timedelta(seconds=3)).adopt(
        context, recovered=recovered, ready=second
    )
    adoptions = store.read_durable_adoptions()
    assert len(adoptions) == 2
    assert isinstance(adoptions[-1].record, ConfigurationAdoptionRecordV2)
    change = store.read_durable_records()[-1].record
    assert 'configuration_rebases' not in change.records
    assert change.records['occurrence_changes']
    assert change.records['episode_changes']
    assert (
        change.snapshot_after.as_document()['state_basis']['alarm_configuration_revision']
        == 'ALARMS-8'
    )
    restored = _recovery(store, versions).recover(Context())
    assert restored.lifecycle.configuration == second.engine
    assert restored.lifecycle.group_for('mill_feed').episode is None
    assert restored.lifecycle.group_for('mill_feed').alarms == ()


def test_mixed_adoption_closes_one_group_and_rebases_another(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    first, second = _ready(), _disabled_ready()
    versions = Materializations(first)
    context = Context()
    _bootstrap(store, versions, context)
    _insert_snapshot(store, active=True)
    _additional_snapshot(store, group='other_group')
    recovered = _recovery(store, versions).recover(context)
    versions.versions[second.result_id] = second
    _adopter(store, versions, at=AT + timedelta(seconds=3)).adopt(
        context, recovered=recovered, ready=second
    )
    final = store.read_durable_adoptions()[-1].record
    assert isinstance(final, ConfigurationAdoptionRecordV2)
    assert tuple(item.priority_group for item in final.group_commits) == (
        'mill_feed',
        'other_group',
    )
    commits = [entry.record for entry in store.read_durable_records()][-2:]
    assert set(commits[0].records) != {'configuration_rebases'}
    assert set(commits[1].records) == {'configuration_rebases'}
    assert restore_group_lifecycle(commits[1].snapshot_after) == GroupLifecycleState(
        priority_group='other_group'
    )
    recovered_again = _recovery(store, versions).recover(Context())
    assert recovered_again.artifact_ref.result_id == second.result_id


def test_withdrawn_technical_incident_is_resolved_in_same_adoption(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    first, second = _ready(), _disabled_ready()
    versions = Materializations(first)
    context = Context()
    _bootstrap(store, versions, context)
    identity = AlarmIdentity('mill', 'risk')
    at = AT + timedelta(seconds=1)
    error = AlarmEvaluation(
        alarm_identity=identity,
        status=AlarmStatus.ERROR,
        evaluated_at=at,
        error=EvaluationError(
            origin=EvaluationErrorOrigin.QUALITY,
            error_key='missing_data',
            message='Missing input',
        ),
    )
    incident = reduce_initial_technical_incidents(
        (), evaluations=(error,), executable_groups={identity: 'mill_feed'}, cycle_at=at
    ).open_incidents[0]
    _additional_snapshot(store, group='mill_feed', incidents=(incident,))
    recovered = _recovery(store, versions).recover(context)
    versions.versions[second.result_id] = second
    _adopter(store, versions, at=AT + timedelta(seconds=3)).adopt(
        context, recovered=recovered, ready=second
    )
    change = store.read_durable_records()[-1].record
    assert change.records['technical_incident_changes'][0]['kind'] == 'RESOLVED'
    assert (
        change.records['technical_incident_changes'][0]['resolution'] == 'CONFIGURATION_WITHDRAWN'
    )
    assert 'configuration_rebases' not in change.records
    assert _recovery(store, versions).recover(Context()).lifecycle.technical_incidents == ()


def test_adoption_after_confirmed_active_cycle_refreshes_group_heads(tmp_path):
    class ActiveCycle:
        def run(self, session):
            at = AT + timedelta(seconds=2)
            return AlarmEvaluationCycleResult(
                cycle_at=at,
                evaluations=tuple(
                    AlarmEvaluation(
                        alarm_identity=entry.identity,
                        status=AlarmStatus.ACTIVE,
                        evaluated_at=at,
                        evidence_snapshot=EvidenceSnapshot(
                            contract_key='test', contract_version='1', payload={'value': 100}
                        ),
                    )
                    for entry in session.entries
                ),
            )

    store = AlarmPersistence(application_root=tmp_path)
    first, second = _ready(), _disabled_ready()
    versions = Materializations(first)
    context = Context()
    job = _job(store, versions, ActiveCycle())
    job.recover(context)
    assert job.run_iteration(context).outcome is AlarmRuntimeConfigurationOutcome.BOOTSTRAPPED
    assert job.run_iteration(context).outcome is AlarmRuntimeConfigurationOutcome.UNCHANGED
    assert store.read_snapshot('mill_feed') is not None
    versions.versions[second.result_id] = second
    versions.published = second
    result = job.run_iteration(context)
    assert result.outcome is AlarmRuntimeConfigurationOutcome.ADOPTED
    assert result.cycle is None
    assert len(store.read_durable_adoptions()) == 2
    assert _recovery(store, versions).recover(Context()).lifecycle.configuration == second.engine


def test_operational_preparation_rejects_stale_snapshot_heads(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    first, second = _ready(), _disabled_ready()
    versions = Materializations(first)
    context = Context()
    _bootstrap(store, versions, context)
    previous = _recovery(store, versions).recover(context)
    _insert_snapshot(store, active=True)
    versions.versions[second.result_id] = second
    adopter = _adopter(store, versions, at=AT + timedelta(seconds=3))
    with pytest.raises(ValueError, match='snapshot inventory'):
        prepare_operational_adoption(
            snapshots=store.list_snapshots(),
            recovered=previous,
            target=second.engine,
            target_ref=adopter.reference_for(second),
            plan=plan_configuration_adoption(previous.lifecycle.configuration, second.engine),
            adoption_id='stale',
            cycle_at=AT + timedelta(seconds=3),
            committed_at=AT + timedelta(seconds=3),
            runtime_artifact_version='runtime/1',
        )
    assert store.read_effective_head().target_artifact_ref.result_id == first.result_id
