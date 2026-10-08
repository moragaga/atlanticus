from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ada.alarms.core import (
    AlarmEpisode,
    AlarmOccurrence,
    AlarmRuntimeState,
    AlarmStatus,
    GroupLifecycleState,
    RuntimeEvaluationState,
)
from ada.alarms.persistence.operational import (
    AlarmArtifactRefSnapshot,
    AlarmPersistence,
    AlarmPersistenceConflictError,
    AlarmPersistenceCorruptionError,
    AlarmPersistenceValidationError,
    ConfigurationAdoptionRecord,
    ConfigurationAdoptionRecordV2,
    EngineCommitMetadata,
    EngineCommitRecord,
    GroupCommitReference,
    GroupRuntimeSnapshot,
    prepare_configuration_rebase,
    prepare_noop_configuration_adoption,
)
from ada.alarms.persistence.operational.lifecycle_snapshot import (
    restore_group_lifecycle,
    snapshot_group_lifecycle,
)
from ada.contracts.alarms import AlarmIdentity

from .support import mutation_fence

AT = datetime(2026, 10, 8, 17, 0, tzinfo=UTC)
IDENTITY = AlarmIdentity('mill', 'risk')


def _ref(char: str, revision: str) -> AlarmArtifactRefSnapshot:
    return AlarmArtifactRefSnapshot(
        source_key='alarm-configuration',
        result_id='alarm-materialization-' + char * 64,
        manifest_sha256=char * 64,
        alarm_configuration_revision=revision,
        confirmed_tool_catalog_revision='TOOLS-4',
    )


def _group_state(group='mill_feed', *, active=False):
    if not active:
        return GroupLifecycleState(priority_group=group)
    occurrence = AlarmOccurrence(
        occurrence_id='O1',
        alarm_identity=IDENTITY,
        episode_id='E1',
        started_at=AT,
        alarm_configuration_revision='R1',
        tool_registry_revision='TOOLS-4',
    )
    alarm = AlarmRuntimeState(
        alarm_identity=IDENTITY,
        occurrence=occurrence,
        last_evaluation=RuntimeEvaluationState(status=AlarmStatus.ACTIVE, evaluated_at=AT),
        management_cycle=1,
    )
    return GroupLifecycleState(
        priority_group=group,
        episode=AlarmEpisode(episode_id='E1', priority_group=group, started_at=AT),
        alarms=(alarm,),
    )


def _baseline(store, group='mill_feed', *, active=False):
    state = _group_state(group, active=active)
    base_time = AT + timedelta(seconds=1)
    snapshot = snapshot_group_lifecycle(
        state,
        commit_id='BASE-' + group,
        alarm_configuration_revision='R1',
        tool_registry_revision='TOOLS-4',
        technical_incidents=(),
    )
    metadata = EngineCommitMetadata(
        commit_id='BASE-' + group,
        cycle_id='BASE',
        priority_group=group,
        previous_commit_id=None,
        evaluated_at=base_time.isoformat().replace('+00:00', 'Z'),
        committed_at=base_time.isoformat().replace('+00:00', 'Z'),
        alarm_configuration_revision='R1',
        tool_registry_revision='TOOLS-4',
        runtime_artifact_version='runtime/1',
        affected_alarms=(IDENTITY.canonical_key,),
    )
    store.commit_batch(
        (EngineCommitRecord.create(commit=metadata, snapshot_after=snapshot),),
        assert_authority=lambda: None,
        fenced_mutation=mutation_fence,
    )
    return snapshot


def _plan(snapshots, *, source=None, target=None, at=None):
    return prepare_noop_configuration_adoption(
        snapshots=snapshots,
        source_ref=_ref('a', 'R1') if source is None else source,
        target_ref=_ref('b', 'R2') if target is None else target,
        adoption_id='adoption-2',
        cycle_at=at or AT + timedelta(seconds=3),
        committed_at=at or AT + timedelta(seconds=3),
        runtime_artifact_version='runtime/1',
    )


def _bootstrap(store):
    reference = _ref('a', 'R1')
    record = ConfigurationAdoptionRecord.create(
        adoption_id='adoption-1',
        previous_artifact_ref=None,
        target_artifact_ref=reference,
        effective_at=AT.isoformat().replace('+00:00', 'Z'),
        committed_at=AT.isoformat().replace('+00:00', 'Z'),
    )
    store.commit_adoption(record, assert_authority=lambda: None, fenced_mutation=mutation_fence)


def test_empty_snapshot_rebases_without_synthetic_alarm_events(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    _bootstrap(store)
    before = _baseline(store)
    planned = _plan((before,))
    assert isinstance(planned.adoption, ConfigurationAdoptionRecordV2)
    assert len(planned.group_records) == 1
    record = planned.group_records[0]
    assert record.commit.affected_alarms == ()
    assert set(record.records) == {'configuration_rebases'}
    assert record.snapshot_after.as_document()['alarms'] == {}
    assert record.snapshot_after.as_document()['technical_incidents'] == {}
    assert restore_group_lifecycle(record.snapshot_after) == restore_group_lifecycle(before)
    store.commit_adoption(
        planned.adoption,
        group_records=planned.group_records,
        assert_authority=lambda: None,
        fenced_mutation=mutation_fence,
    )
    restarted = AlarmPersistence(application_root=tmp_path)
    restarted.recover(assert_authority=lambda: None, fenced_mutation=mutation_fence)
    assert restarted.read_effective_head().target_artifact_ref == _ref('b', 'R2')
    assert restarted.read_snapshot('mill_feed') == record.snapshot_after
    assert len(restarted.read_durable_adoptions()) == 2


def test_open_occurrence_identity_and_state_are_preserved(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    _bootstrap(store)
    before = _baseline(store, active=True)
    planned = _plan((before,))
    after = planned.group_records[0].snapshot_after
    assert planned.group_records[0].commit.affected_alarms == (IDENTITY.canonical_key,)
    assert restore_group_lifecycle(before) == restore_group_lifecycle(after)
    old_state = before.as_document()
    new_state = after.as_document()
    assert old_state['episode'] == new_state['episode']
    assert (
        old_state['alarms']['mill/risk']['occurrence']
        == new_state['alarms']['mill/risk']['occurrence']
    )
    assert new_state['state_basis']['alarm_configuration_revision'] == 'R2'
    assert new_state['alarms']['mill/risk']['last_commit_id'] == after.last_commit_id


def test_multiple_groups_are_sorted_and_commit_references_match(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    _bootstrap(store)
    first = _baseline(store, group='z_group')
    second = _baseline(store, group='a_group')
    planned = _plan((first, second))
    assert tuple(record.commit.priority_group for record in planned.group_records) == (
        'a_group',
        'z_group',
    )
    assert tuple(ref.record_hash for ref in planned.adoption.group_commits) == tuple(
        record.record_hash for record in planned.group_records
    )
    store.commit_adoption(
        planned.adoption,
        group_records=planned.group_records,
        assert_authority=lambda: None,
        fenced_mutation=mutation_fence,
    )
    assert store.read_effective_head().target_artifact_ref == _ref('b', 'R2')


def test_bootstrap_with_no_groups_uses_adoption_v1():
    result = prepare_noop_configuration_adoption(
        snapshots=(),
        source_ref=None,
        target_ref=_ref('a', 'R1'),
        adoption_id='first',
        cycle_at=AT,
        committed_at=AT,
        runtime_artifact_version='runtime/1',
    )
    assert type(result.adoption) is ConfigurationAdoptionRecord
    assert result.group_records == ()


def test_unchanged_group_basis_requires_matching_previous_revision(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    _bootstrap(store)
    before = _baseline(store)
    with pytest.raises(ValueError, match='basis'):
        prepare_configuration_rebase(
            previous_snapshot=before,
            source_ref=_ref('a', 'WRONG'),
            target_ref=_ref('b', 'R2'),
            cycle_at=AT + timedelta(seconds=3),
            committed_at=AT + timedelta(seconds=3),
            runtime_artifact_version='runtime/1',
        )


def test_rebase_rejects_snapshot_forgery_before_wal(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    _bootstrap(store)
    before = _baseline(store, active=True)
    planned = _plan((before,))
    record = planned.group_records[0]
    forged_doc = record.snapshot_after.as_document()
    forged_doc['episode']['episode_id'] = 'DIFFERENT'
    forged = EngineCommitRecord.create(
        commit=record.commit,
        snapshot_after=GroupRuntimeSnapshot(forged_doc),
        records=record.records,
    )
    updated_adoption = ConfigurationAdoptionRecordV2.create(
        adoption_id=planned.adoption.adoption_id,
        previous_artifact_ref=planned.adoption.previous_artifact_ref,
        target_artifact_ref=planned.adoption.target_artifact_ref,
        effective_at=planned.adoption.effective_at,
        committed_at=planned.adoption.committed_at,
        group_commits=(
            GroupCommitReference(
                priority_group=forged.commit.priority_group,
                commit_id=forged.commit.commit_id,
                record_hash=forged.record_hash,
            ),
        ),
    )
    with pytest.raises(AlarmPersistenceConflictError, match='changed operational'):
        store.commit_adoption(
            updated_adoption,
            group_records=(forged,),
            assert_authority=lambda: None,
            fenced_mutation=mutation_fence,
        )
    assert store.read_effective_head().target_artifact_ref == _ref('a', 'R1')


def test_rebase_rejects_record_mixed_with_physical_event(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    _bootstrap(store)
    before = _baseline(store)
    record = _plan((before,)).group_records[0]
    with pytest.raises(AlarmPersistenceValidationError, match='exclusive'):
        EngineCommitRecord.create(
            commit=record.commit,
            snapshot_after=record.snapshot_after,
            records={**record.records, 'journey_events': [{'event_id': 'FAKE'}]},
        )


def test_rebase_rejects_legacy_snapshot_and_duplicate_group():
    snapshot = snapshot_group_lifecycle(
        _group_state(),
        commit_id='C1',
        alarm_configuration_revision='R1',
        tool_registry_revision='TOOLS-4',
        technical_incidents=(),
    )
    doc = snapshot.as_document()
    doc['snapshot_schema_version'] = 'group-runtime-snapshot.v2'
    legacy = GroupRuntimeSnapshot(doc)
    with pytest.raises(ValueError, match='snapshot v3'):
        _plan((legacy,))
    with pytest.raises(ValueError, match='unique'):
        _plan((snapshot, snapshot))


def test_rebase_rejects_stale_snapshot_during_atomic_adoption(tmp_path):
    store = AlarmPersistence(application_root=tmp_path)
    _bootstrap(store)
    first = _baseline(store)
    plan = _plan((first,))
    changed = _plan((first,), at=AT + timedelta(seconds=5))
    store.commit_adoption(
        changed.adoption,
        group_records=changed.group_records,
        assert_authority=lambda: None,
        fenced_mutation=mutation_fence,
    )
    with pytest.raises(AlarmPersistenceConflictError):
        store.commit_adoption(
            plan.adoption,
            group_records=plan.group_records,
            assert_authority=lambda: None,
            fenced_mutation=mutation_fence,
        )


def test_rebase_roundtrip_and_hash_rejection():
    snapshot = snapshot_group_lifecycle(
        _group_state(),
        commit_id='C1',
        alarm_configuration_revision='R1',
        tool_registry_revision='TOOLS-4',
        technical_incidents=(),
    )
    record = _plan((snapshot,)).group_records[0]
    assert EngineCommitRecord.from_document(record.as_document()) == record
    tampered = record.as_document()
    tampered['records']['configuration_rebases'][0]['target_basis'][
        'alarm_configuration_revision'
    ] = 'FAKE'
    with pytest.raises(AlarmPersistenceCorruptionError):
        EngineCommitRecord.from_document(tampered)
