from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace

import pytest

from ada.alarms.persistence.operational import (
    AlarmArtifactRefSnapshot,
    AlarmPersistence,
    AlarmPersistenceCorruptionError,
    AlarmRecoveryRequiredError,
    ConfigurationAdoptionRecord,
    ConfigurationAdoptionRecordV2,
    GroupCommitReference,
    JournalPosition,
)

from .support import build_record, mutation_fence


def _ref(letter: str) -> AlarmArtifactRefSnapshot:
    return AlarmArtifactRefSnapshot(
        source_key='alarm-configuration',
        result_id='alarm-materialization-' + letter * 64,
        manifest_sha256=letter * 64,
        alarm_configuration_revision='R42',
        confirmed_tool_catalog_revision='T18',
    )


def _adopt(store: AlarmPersistence, letter: str, previous=None) -> None:
    store.commit_adoption(
        ConfigurationAdoptionRecord.create(
            adoption_id='adoption-' + letter,
            previous_artifact_ref=previous,
            target_artifact_ref=_ref(letter),
            effective_at='2026-08-23T20:00:00Z',
            committed_at='2026-08-23T20:00:00Z',
        ),
        assert_authority=lambda: None,
        fenced_mutation=mutation_fence,
    )


def _commit(store: AlarmPersistence, *records) -> None:
    store.commit_batch(
        records,
        assert_authority=lambda: None,
        fenced_mutation=mutation_fence,
    )


def _v2(store: AlarmPersistence, *, letter='a', previous=None) -> None:
    first = build_record(commit_id='A1', priority_group='a', alarm_key='alarm_a')
    second = build_record(commit_id='B1', priority_group='b', alarm_key='alarm_b')
    group_records = (first, second)
    adoption = ConfigurationAdoptionRecordV2.create(
        adoption_id='adoption-v2-' + letter,
        previous_artifact_ref=previous,
        target_artifact_ref=_ref(letter),
        effective_at='2026-08-23T20:00:00Z',
        committed_at='2026-08-23T20:00:00Z',
        group_commits=tuple(
            GroupCommitReference(
                priority_group=item.commit.priority_group,
                commit_id=item.commit.commit_id,
                record_hash=item.record_hash,
            )
            for item in group_records
        ),
    )
    store.commit_adoption(
        adoption,
        group_records=group_records,
        assert_authority=lambda: None,
        fenced_mutation=mutation_fence,
    )


def test_empty_wal_has_no_provenance(tmp_path) -> None:
    store = AlarmPersistence(application_root=tmp_path)
    assert store.read_durable_provenance() == ()


def test_v1_and_commits_keep_exact_artifact_across_same_revision_adoption(tmp_path) -> None:
    store = AlarmPersistence(application_root=tmp_path)
    _adopt(store, 'a')
    _commit(store, build_record(commit_id='C1'))
    _adopt(store, 'b', previous=_ref('a'))
    _commit(store, build_record(commit_id='C2', previous_commit_id='C1', cycle_id='second'))
    rows = store.read_durable_provenance()
    assert [row.entry.end.commit_id for row in rows] == ['adoption-a', 'C1', 'adoption-b', 'C2']
    assert [row.artifact_ref for row in rows] == [_ref('a'), _ref('a'), _ref('b'), _ref('b')]
    assert len({row.entry.end for row in rows}) == 4
    assert rows[0].entry.record.target_artifact_ref == _ref('a')


def test_v2_group_commits_are_attributed_to_target_before_adoption_record(tmp_path) -> None:
    store = AlarmPersistence(application_root=tmp_path)
    _v2(store)
    rows = store.read_durable_provenance()
    assert [row.entry.end.commit_id for row in rows] == ['A1', 'B1', 'adoption-v2-a']
    assert all(row.artifact_ref == _ref('a') for row in rows)
    assert isinstance(rows[-1].entry.record, ConfigurationAdoptionRecordV2)


def test_v2_cursor_inside_confirmed_batch_keeps_remaining_order(tmp_path) -> None:
    store = AlarmPersistence(application_root=tmp_path)
    _v2(store)
    rows = store.read_durable_provenance()
    assert store.read_durable_provenance(after=rows[0].entry.end) == rows[1:]
    assert store.read_durable_provenance(after=rows[-1].entry.end) == ()


def test_unknown_cursor_cannot_skip_history(tmp_path) -> None:
    store = AlarmPersistence(application_root=tmp_path)
    _v2(store)
    first = store.read_durable_provenance()[0]
    invalid = replace(first.entry.end, commit_id='not-in-wal')
    with pytest.raises(ValueError, match='exact durable'):
        store.read_durable_provenance(after=invalid)
    with pytest.raises(ValueError, match='exact durable'):
        store.read_durable_provenance(
            after=JournalPosition(
                segment_id=first.entry.end.segment_id,
                byte_offset=first.entry.end.byte_offset + 999999,
                commit_id='unknown',
            )
        )
    with pytest.raises(TypeError, match='JournalPosition'):
        store.read_durable_provenance(after='invalid')


def test_old_commit_only_wal_cannot_claim_exact_provenance(tmp_path) -> None:
    store = AlarmPersistence(application_root=tmp_path)
    _commit(store, build_record(commit_id='C1'))
    with pytest.raises(AlarmPersistenceCorruptionError, match='origin'):
        store.read_durable_provenance()


def test_pending_recovery_blocks_provenance_read(tmp_path, monkeypatch) -> None:
    store = AlarmPersistence(application_root=tmp_path)
    original = store._materialize_entry

    def crash(_entry):
        raise RuntimeError('crash after durable')

    monkeypatch.setattr(store, '_materialize_entry', crash)
    record = build_record(commit_id='A1', priority_group='a', alarm_key='alarm_a')
    adoption = ConfigurationAdoptionRecordV2.create(
        adoption_id='adoption-v2-a',
        previous_artifact_ref=None,
        target_artifact_ref=_ref('a'),
        effective_at='2026-08-23T20:00:00Z',
        committed_at='2026-08-23T20:00:00Z',
        group_commits=(
            GroupCommitReference(
                priority_group='a', commit_id='A1', record_hash=record.record_hash
            ),
        ),
    )
    with pytest.raises(RuntimeError, match='crash after durable'):
        store.commit_adoption(
            adoption,
            group_records=(record,),
            assert_authority=lambda: None,
            fenced_mutation=lambda: nullcontext(),
        )
    with pytest.raises(AlarmRecoveryRequiredError, match='recovered'):
        store.read_durable_provenance()
    monkeypatch.setattr(store, '_materialize_entry', original)
    store.recover(assert_authority=lambda: None, fenced_mutation=mutation_fence)
    assert len(store.read_durable_provenance()) == 2


def test_after_cursor_on_empty_wal_is_rejected(tmp_path) -> None:
    store = AlarmPersistence(application_root=tmp_path)
    after = JournalPosition(
        segment_id='2026-08-23T20Z#0000',
        byte_offset=10,
        commit_id='A1',
    )
    with pytest.raises(ValueError, match='exact durable'):
        store.read_durable_provenance(after=after)
