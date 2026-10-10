from __future__ import annotations

import pytest

from ada.alarms.persistence.operational import (
    AlarmArtifactRefSnapshot,
    AlarmPersistenceCorruptionError,
    ConfigurationAdoptionRecord,
    JournalPosition,
)
from ada.alarms.persistence.operational.incremental import IncrementalAlarmPersistence
from ada.alarms.persistence.operational.recovery_checkpoint import (
    RecoveryCheckpoint,
    latest_checkpoint,
)

from .support import build_record, mutation_fence


def _authority() -> None:
    return None


def _ref() -> AlarmArtifactRefSnapshot:
    return AlarmArtifactRefSnapshot(
        source_key='alarm-configuration',
        result_id='alarm-materialization-' + 'a' * 64,
        manifest_sha256='a' * 64,
        alarm_configuration_revision='R42',
        confirmed_tool_catalog_revision='T18',
    )


def _make_store(tmp_path) -> IncrementalAlarmPersistence:
    store = IncrementalAlarmPersistence(application_root=tmp_path)
    store.commit_adoption(
        ConfigurationAdoptionRecord.create(
            adoption_id='adoption-a',
            previous_artifact_ref=None,
            target_artifact_ref=_ref(),
            effective_at='2026-08-23T20:00:00Z',
            committed_at='2026-08-23T20:00:00Z',
        ),
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )
    store.commit_batch(
        (build_record(commit_id='C1'),),
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )
    return store


def test_checkpoint_is_idempotent_and_two_slots_are_bounded(tmp_path) -> None:
    store = _make_store(tmp_path)
    assert store.publish_recovery_checkpoint(
        assert_authority=_authority, fenced_mutation=mutation_fence
    )
    assert not store.publish_recovery_checkpoint(
        assert_authority=_authority, fenced_mutation=mutation_fence
    )
    store.commit_batch(
        (build_record(commit_id='C2', previous_commit_id='C1', cycle_id='second'),),
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )
    assert store.publish_recovery_checkpoint(
        assert_authority=_authority, fenced_mutation=mutation_fence
    )
    checkpoints = tuple(item for item in store._checkpoint_slots() if item is not None)
    assert len(checkpoints) == 2
    assert sorted(item.sequence for item in checkpoints) == [1, 2]
    assert latest_checkpoint(checkpoints).journal_head == store.read_head().as_document()


def test_exact_checkpoint_recovery_does_not_rescan_historical_wal(tmp_path, monkeypatch) -> None:
    store = _make_store(tmp_path)
    store.publish_recovery_checkpoint(assert_authority=_authority, fenced_mutation=mutation_fence)
    restarted = IncrementalAlarmPersistence(application_root=tmp_path)

    def forbid_rescan(_durable):
        raise AssertionError('checkpoint recovery must not replay the entire WAL')

    monkeypatch.setattr(restarted._journal, 'validate_durable_region', forbid_rescan)
    result = restarted.recover(assert_authority=_authority, fenced_mutation=mutation_fence)
    assert result.durable == store.read_head().durable
    assert restarted.read_effective_head().target_artifact_ref == _ref()
    assert restarted.read_snapshot('crusher_pressure').last_commit_id == 'C1'


def test_stale_checkpoint_recovers_newer_durable_commit(tmp_path) -> None:
    store = _make_store(tmp_path)
    store.publish_recovery_checkpoint(assert_authority=_authority, fenced_mutation=mutation_fence)
    checkpoint = latest_checkpoint(store._checkpoint_slots())
    assert checkpoint is not None
    checkpoint_position = JournalPosition.from_document(checkpoint.journal_head['durable'])
    store.commit_batch(
        (build_record(commit_id='C2', previous_commit_id='C1', cycle_id='second'),),
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )
    expected_head = store.read_head()
    restarted = IncrementalAlarmPersistence(application_root=tmp_path)
    recovered = restarted.recover(assert_authority=_authority, fenced_mutation=mutation_fence)
    assert recovered.durable == expected_head.durable
    assert recovered.materialized == expected_head.materialized
    assert restarted.read_snapshot('crusher_pressure').last_commit_id == 'C2'
    assert [
        entry.entry.record.commit.commit_id
        for entry in restarted.read_durable_provenance(after=checkpoint_position)
    ] == ['C2']


def test_checkpoint_rejects_tampering_of_snapshots_and_wal(tmp_path) -> None:
    store = _make_store(tmp_path)
    store.publish_recovery_checkpoint(assert_authority=_authority, fenced_mutation=mutation_fence)
    snapshot_path = store.paths.alarms_root / store.paths.group_snapshot_relative(
        'crusher_pressure'
    )
    old = snapshot_path.read_bytes()
    snapshot_path.write_bytes(old.replace(b'C1', b'Z1', 1))
    with pytest.raises(AlarmPersistenceCorruptionError):
        IncrementalAlarmPersistence(application_root=tmp_path).recover(
            assert_authority=_authority, fenced_mutation=mutation_fence
        )
    snapshot_path.write_bytes(old)
    wal_path = next((tmp_path / 'alarms' / 'runtime' / 'journal').rglob('part-*.jsonl'))
    wal = wal_path.read_bytes()
    wal_path.write_bytes(wal.replace(b'C1', b'Z1', 1))
    with pytest.raises(AlarmPersistenceCorruptionError, match='WAL anchor'):
        IncrementalAlarmPersistence(application_root=tmp_path).recover(
            assert_authority=_authority, fenced_mutation=mutation_fence
        )


def test_checkpoint_checksum_detects_document_corruption() -> None:
    document = RecoveryCheckpoint.create(
        sequence=1,
        journal_head={
            'journal_head_schema_version': 'journal-head.v1',
            'durable': {'commit_id': 'C1', 'byte_offset': 50, 'segment_id': '2026-08-23T20Z#0000'},
            'materialized': {
                'commit_id': 'C1',
                'byte_offset': 50,
                'segment_id': '2026-08-23T20Z#0000',
            },
        },
        effective_head={'adoption_id': 'a'},
        groups=[{'priority_group': 'a'}],
        wal_anchor_sha256='a' * 64,
    )
    corrupted = document.as_document()
    corrupted['groups'] = [{'priority_group': 'b'}]
    with pytest.raises(ValueError, match='integrity'):
        RecoveryCheckpoint.from_document(corrupted)


def _compacted_store(tmp_path):
    store = _make_store(tmp_path)
    assert store.publish_recovery_checkpoint(
        assert_authority=_authority, fenced_mutation=mutation_fence
    )
    for hour, commit_id, previous in (
        (21, 'C2', 'C1'),
        (22, 'C3', 'C2'),
    ):
        store.commit_batch(
            (
                build_record(
                    commit_id=commit_id,
                    previous_commit_id=previous,
                    cycle_id=f'cycle-{hour}',
                    evaluated_at=f'2026-08-23T{hour:02d}:00:00Z',
                ),
            ),
            assert_authority=_authority,
            fenced_mutation=mutation_fence,
        )
        assert store.publish_recovery_checkpoint(
            assert_authority=_authority, fenced_mutation=mutation_fence
        )
    return store


def test_compaction_removes_only_old_sealed_wal_and_recovers_exact_state(tmp_path) -> None:
    store = _compacted_store(tmp_path)
    before = store.read_snapshot('crusher_pressure').as_document()
    sealed = store._journal._discover_sealed_segments()
    assert len(sealed) == 2
    assert (
        store.compact_recovered_wal(
            exported_through=store.read_head().durable,
            assert_authority=_authority,
            fenced_mutation=mutation_fence,
        )
        > 0
    )
    remaining = store._journal.discover_segments()
    assert len(remaining) == 2
    assert not any(segment.startswith('2026-08-23T20') for segment in remaining)
    restarted = IncrementalAlarmPersistence(application_root=tmp_path)
    restarted.recover(assert_authority=_authority, fenced_mutation=mutation_fence)
    assert restarted.read_snapshot('crusher_pressure').as_document() == before
    assert restarted.read_effective_head().target_artifact_ref == _ref()
    assert not restarted.compact_recovered_wal(
        exported_through=restarted.read_head().durable,
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )


def test_compaction_fails_closed_before_facts_export(tmp_path) -> None:
    store = _compacted_store(tmp_path)
    assert (
        store.compact_recovered_wal(
            exported_through=None,
            assert_authority=_authority,
            fenced_mutation=mutation_fence,
        )
        == 0
    )
    assert any(
        segment.startswith('2026-08-23T20') for segment in store._journal.discover_segments()
    )


def test_compacted_wal_restart_recovers_commits_after_checkpoint(tmp_path) -> None:
    store = _compacted_store(tmp_path)
    assert (
        store.compact_recovered_wal(
            exported_through=store.read_head().durable,
            assert_authority=_authority,
            fenced_mutation=mutation_fence,
        )
        > 0
    )
    store.commit_batch(
        (
            build_record(
                commit_id='C4',
                previous_commit_id='C3',
                cycle_id='cycle-23',
                evaluated_at='2026-08-23T23:00:00Z',
            ),
        ),
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )
    restarted = IncrementalAlarmPersistence(application_root=tmp_path)
    recovered = restarted.recover(assert_authority=_authority, fenced_mutation=mutation_fence)
    assert recovered.durable == store.read_head().durable
    assert restarted.read_snapshot('crusher_pressure').last_commit_id == 'C4'
    assert restarted.read_effective_head().target_artifact_ref == _ref()
    position = JournalPosition.from_document(
        latest_checkpoint(store._checkpoint_slots()).journal_head['durable']
    )
    rows = restarted.read_durable_provenance(after=position)
    assert [item.entry.record.commit.commit_id for item in rows] == ['C4']
    assert rows[0].artifact_ref == _ref()


def test_compacted_wal_crash_between_durable_and_materialized_is_recovered(
    tmp_path, monkeypatch
) -> None:
    store = _compacted_store(tmp_path)
    store.compact_recovered_wal(
        exported_through=store.read_head().durable,
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )

    def interrupt(_entry):
        raise RuntimeError('simulated materialization interruption')

    monkeypatch.setattr(store, '_materialize_entry', interrupt)
    with pytest.raises(RuntimeError, match='simulated materialization interruption'):
        store.commit_batch(
            (
                build_record(
                    commit_id='C4',
                    previous_commit_id='C3',
                    cycle_id='cycle-23',
                    evaluated_at='2026-08-23T23:00:00Z',
                ),
            ),
            assert_authority=_authority,
            fenced_mutation=mutation_fence,
        )
    restarted = IncrementalAlarmPersistence(application_root=tmp_path)
    restarted.recover(assert_authority=_authority, fenced_mutation=mutation_fence)
    assert restarted.read_head().aligned
    assert restarted.read_snapshot('crusher_pressure').last_commit_id == 'C4'


def test_compacted_wal_suffix_tampering_fails_closed(tmp_path) -> None:
    store = _compacted_store(tmp_path)
    store.compact_recovered_wal(
        exported_through=store.read_head().durable,
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )
    store.commit_batch(
        (
            build_record(
                commit_id='C4',
                previous_commit_id='C3',
                cycle_id='cycle-23',
                evaluated_at='2026-08-23T23:00:00Z',
            ),
        ),
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )
    newest = max(store._journal.discover_segments())
    path = store._journal.discover_segments()[newest]
    data = path.read_bytes()
    path.write_bytes(data.replace(b'C4', b'Z4', 1))
    with pytest.raises(AlarmPersistenceCorruptionError):
        IncrementalAlarmPersistence(application_root=tmp_path).recover(
            assert_authority=_authority,
            fenced_mutation=mutation_fence,
        )


def test_interrupted_compaction_can_be_retried_without_losing_recovery(
    tmp_path, monkeypatch
) -> None:
    store = _compacted_store(tmp_path)
    store.commit_batch(
        (
            build_record(
                commit_id='C4',
                previous_commit_id='C3',
                cycle_id='cycle-23',
                evaluated_at='2026-08-23T23:00:00Z',
            ),
        ),
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )
    assert store.publish_recovery_checkpoint(
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )
    candidates = store._journal._discover_sealed_segments()
    assert len(candidates) == 3
    original_unlink = type(next(iter(candidates.values()))).unlink
    count = 0

    def interrupted_unlink(path, *args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError('simulated interruption')
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(type(next(iter(candidates.values()))), 'unlink', interrupted_unlink)
    with pytest.raises(Exception, match='could not remove compacted WAL segment'):
        store.compact_recovered_wal(
            exported_through=store.read_head().durable,
            assert_authority=_authority,
            fenced_mutation=mutation_fence,
        )
    monkeypatch.setattr(type(next(iter(candidates.values()))), 'unlink', original_unlink)
    restarted = IncrementalAlarmPersistence(application_root=tmp_path)
    restarted.recover(assert_authority=_authority, fenced_mutation=mutation_fence)
    assert restarted.read_snapshot('crusher_pressure').last_commit_id == 'C4'
    assert (
        restarted.compact_recovered_wal(
            exported_through=restarted.read_head().durable,
            assert_authority=_authority,
            fenced_mutation=mutation_fence,
        )
        > 0
    )
    assert restarted.read_head().aligned


def test_checkpoint_backup_anchor_cannot_be_removed_when_corrupted(tmp_path) -> None:
    store = _compacted_store(tmp_path)
    slots = sorted(store._checkpoint_slots(), key=lambda item: item.sequence)
    older = JournalPosition.from_document(slots[0].journal_head['durable'])
    path = store._journal._resolve_segment_path(older.segment_id)
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b'C2', b'Z2', 1))
    with pytest.raises(AlarmPersistenceCorruptionError, match='backup WAL anchor'):
        store.compact_recovered_wal(
            exported_through=store.read_head().durable,
            assert_authority=_authority,
            fenced_mutation=mutation_fence,
        )
    assert any(
        segment.startswith('2026-08-23T20') for segment in store._journal.discover_segments()
    )
