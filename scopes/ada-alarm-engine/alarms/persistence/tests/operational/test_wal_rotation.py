from __future__ import annotations

from dataclasses import replace

import pytest

from ada.alarms.persistence.operational import (
    AlarmArtifactRefSnapshot,
    AlarmPersistenceCorruptionError,
    ConfigurationAdoptionRecord,
)
from ada.alarms.persistence.operational.incremental import IncrementalAlarmPersistence

from .support import build_record, mutation_fence


def _authority() -> None:
    return None


def _store(root, *, segment_bytes: int = 512) -> IncrementalAlarmPersistence:
    store = IncrementalAlarmPersistence(
        application_root=root,
        max_journal_segment_bytes=segment_bytes,
    )
    reference = AlarmArtifactRefSnapshot(
        source_key='alarm-configuration',
        result_id='alarm-materialization-' + 'a' * 64,
        manifest_sha256='a' * 64,
        alarm_configuration_revision='R42',
        confirmed_tool_catalog_revision='T18',
    )
    store.commit_adoption(
        ConfigurationAdoptionRecord.create(
            adoption_id='adoption-a',
            previous_artifact_ref=None,
            target_artifact_ref=reference,
            effective_at='2026-08-23T20:00:00Z',
            committed_at='2026-08-23T20:00:00Z',
        ),
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )
    return store


def _commit(store: IncrementalAlarmPersistence, index: int) -> None:
    store.commit_batch(
        (
            build_record(
                commit_id=f'C{index}',
                previous_commit_id=None if index == 1 else f'C{index - 1}',
                cycle_id=f'cycle-{index}',
            ),
        ),
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )


def _checkpoint(store: IncrementalAlarmPersistence) -> None:
    assert store.publish_recovery_checkpoint(
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )


def test_rotates_within_same_hour_and_keeps_committed_batches_atomic(tmp_path) -> None:
    store = _store(tmp_path)
    for index in range(1, 5):
        _commit(store, index)
    segments = store._journal.discover_segments()
    assert len(segments) == 5
    assert sorted(segments) == [f'2026-08-23T20Z#{index:04d}' for index in range(5)]
    assert len(store.read_durable_provenance()) == 5
    assert store.read_head().durable.segment_id.endswith('#0004')
    restarted = IncrementalAlarmPersistence(application_root=tmp_path)
    restarted.recover(assert_authority=_authority, fenced_mutation=mutation_fence)
    assert restarted.read_snapshot('crusher_pressure').last_commit_id == 'C4'


def test_compacts_during_operation_but_preserves_backup_and_recovery(tmp_path) -> None:
    store = _store(tmp_path)
    _commit(store, 1)
    _checkpoint(store)
    _commit(store, 2)
    _checkpoint(store)
    _commit(store, 3)
    _checkpoint(store)
    head = store.read_head().durable
    paths_before = store._journal.discover_segments()
    assert (
        store.compact_recovered_wal(
            exported_through=replace(head, commit_id='wrong'),
            assert_authority=_authority,
            fenced_mutation=mutation_fence,
        )
        == 0
    )
    assert store._journal.discover_segments() == paths_before
    removed = store.compact_recovered_wal(
        exported_through=head,
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )
    assert removed > 0
    assert len(store._journal.discover_segments()) < len(paths_before)
    assert (
        store.compact_recovered_wal(
            exported_through=head,
            assert_authority=_authority,
            fenced_mutation=mutation_fence,
        )
        == 0
    )
    backup, latest = sorted(store._checkpoint_slots(), key=lambda value: value.sequence)
    assert backup.journal_head['durable']['segment_id'] in store._journal.discover_segments()
    restarted = IncrementalAlarmPersistence(application_root=tmp_path)
    restarted.recover(assert_authority=_authority, fenced_mutation=mutation_fence)
    assert restarted.read_snapshot('crusher_pressure').last_commit_id == 'C3'
    _commit(restarted, 4)
    assert restarted.read_snapshot('crusher_pressure').last_commit_id == 'C4'


def test_recovery_of_confirmed_unmaterialized_commit_after_rotation(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path)
    _commit(store, 1)
    _checkpoint(store)
    original = store._materialize_entry

    def fail(_entry):
        raise RuntimeError('simulated crash after durable head')

    monkeypatch.setattr(store, '_materialize_entry', fail)
    with pytest.raises(RuntimeError, match='simulated crash'):
        _commit(store, 2)
    monkeypatch.setattr(store, '_materialize_entry', original)
    restarted = IncrementalAlarmPersistence(application_root=tmp_path)
    restarted.recover(assert_authority=_authority, fenced_mutation=mutation_fence)
    assert restarted.read_head().aligned
    assert restarted.read_snapshot('crusher_pressure').last_commit_id == 'C2'


def test_rejects_corruption_in_active_rotated_wal(tmp_path) -> None:
    store = _store(tmp_path)
    _commit(store, 1)
    _checkpoint(store)
    _commit(store, 2)
    target = store._journal._resolve_segment_path(store.read_head().durable.segment_id)
    payload = target.read_bytes()
    target.write_bytes(payload.replace(b'C2', b'Z2', 1))
    with pytest.raises(AlarmPersistenceCorruptionError):
        IncrementalAlarmPersistence(application_root=tmp_path).recover(
            assert_authority=_authority,
            fenced_mutation=mutation_fence,
        )


def test_v2_adoption_batch_is_never_split_by_size_rotation(tmp_path) -> None:
    from ada.alarms.persistence.operational import (
        ConfigurationAdoptionRecordV2,
        GroupCommitReference,
    )

    store = _store(tmp_path)
    previous = store.read_effective_head().target_artifact_ref
    target = AlarmArtifactRefSnapshot(
        source_key='alarm-configuration',
        result_id='alarm-materialization-' + 'b' * 64,
        manifest_sha256='b' * 64,
        alarm_configuration_revision='R42',
        confirmed_tool_catalog_revision='T18',
    )
    group_records = (
        build_record(commit_id='A1', priority_group='a', alarm_key='alarm_a'),
        build_record(commit_id='B1', priority_group='b', alarm_key='alarm_b'),
    )
    adoption = ConfigurationAdoptionRecordV2.create(
        adoption_id='adoption-b',
        previous_artifact_ref=previous,
        target_artifact_ref=target,
        effective_at='2026-08-23T20:00:00Z',
        committed_at='2026-08-23T20:00:00Z',
        group_commits=tuple(
            GroupCommitReference(
                priority_group=record.commit.priority_group,
                commit_id=record.commit.commit_id,
                record_hash=record.record_hash,
            )
            for record in group_records
        ),
    )
    before = store.read_head().durable
    store.commit_adoption(
        adoption,
        group_records=group_records,
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )
    items = store.read_durable_provenance(after=before)
    assert len(items) == 3
    assert len({item.entry.end.segment_id for item in items}) == 1
    assert items[0].entry.end.segment_id != before.segment_id
    assert all(item.artifact_ref == target for item in items)


def test_restart_can_advance_after_interrupted_segment_sealing(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path)
    _commit(store, 1)
    original = store._journal.append_batch

    def interrupted(*args, **kwargs):
        raise RuntimeError('simulated failure after sealing')

    monkeypatch.setattr(store._journal, 'append_batch', interrupted)
    with pytest.raises(RuntimeError, match='simulated failure after sealing'):
        _commit(store, 2)
    monkeypatch.setattr(store._journal, 'append_batch', original)
    restarted = IncrementalAlarmPersistence(
        application_root=tmp_path,
        max_journal_segment_bytes=262144,
    )
    restarted.recover(assert_authority=_authority, fenced_mutation=mutation_fence)
    _commit(restarted, 2)
    assert restarted.read_snapshot('crusher_pressure').last_commit_id == 'C2'
    assert restarted.read_head().durable.segment_id.endswith('#0002')
