from __future__ import annotations

from dataclasses import replace

import pytest

from ada.alarms.persistence.operational import (
    AlarmArtifactRefSnapshot,
    AlarmPersistenceCorruptionError,
    AlarmRecoveryRequiredError,
    ConfigurationAdoptionRecord,
    ConfigurationAdoptionRecordV2,
    GroupCommitReference,
)
from ada.alarms.persistence.operational.incremental import IncrementalAlarmPersistence

from .support import build_record, mutation_fence


def _authority() -> None:
    return None


def _ref(letter: str) -> AlarmArtifactRefSnapshot:
    return AlarmArtifactRefSnapshot(
        source_key='alarm-configuration',
        result_id='alarm-materialization-' + letter * 64,
        manifest_sha256=letter * 64,
        alarm_configuration_revision='R42',
        confirmed_tool_catalog_revision='T18',
    )


def _adopt(store: IncrementalAlarmPersistence, letter: str, previous=None) -> None:
    store.commit_adoption(
        ConfigurationAdoptionRecord.create(
            adoption_id='adoption-' + letter,
            previous_artifact_ref=previous,
            target_artifact_ref=_ref(letter),
            effective_at='2026-08-23T20:00:00Z',
            committed_at='2026-08-23T20:00:00Z',
        ),
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )


def _commit(store: IncrementalAlarmPersistence, record) -> None:
    store.commit_batch(
        (record,),
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )


def test_warm_commit_and_provenance_do_not_rescan_historical_wal(tmp_path, monkeypatch) -> None:
    store = IncrementalAlarmPersistence(application_root=tmp_path)
    _adopt(store, 'a')
    first = build_record(commit_id='C1')
    _commit(store, first)
    cursor = store.read_head().durable
    calls = 0
    original = store._journal.validate_durable_region

    def monitored(durable):
        nonlocal calls
        calls += 1
        return original(durable)

    monkeypatch.setattr(store._journal, 'validate_durable_region', monitored)
    second = build_record(commit_id='C2', previous_commit_id='C1', cycle_id='second')
    _commit(store, second)
    rows = store.read_durable_provenance(after=cursor)
    assert [row.entry.record for row in rows] == [second]
    assert rows[0].artifact_ref == _ref('a')
    assert store.read_effective_head().target_artifact_ref == _ref('a')
    assert calls == 0
    assert store.read_durable_provenance(after=rows[-1].entry.end) == ()


def test_v2_adoption_attributes_commits_before_adoption(tmp_path) -> None:
    store = IncrementalAlarmPersistence(application_root=tmp_path)
    records = (
        build_record(commit_id='A1', priority_group='a', alarm_key='alarm_a'),
        build_record(commit_id='B1', priority_group='b', alarm_key='alarm_b'),
    )
    adoption = ConfigurationAdoptionRecordV2.create(
        adoption_id='adoption-v2-a',
        previous_artifact_ref=None,
        target_artifact_ref=_ref('a'),
        effective_at='2026-08-23T20:00:00Z',
        committed_at='2026-08-23T20:00:00Z',
        group_commits=tuple(
            GroupCommitReference(
                priority_group=record.commit.priority_group,
                commit_id=record.commit.commit_id,
                record_hash=record.record_hash,
            )
            for record in records
        ),
    )
    store.commit_adoption(
        adoption,
        group_records=records,
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )
    rows = store.read_durable_provenance()
    assert [row.entry.end.commit_id for row in rows] == ['A1', 'B1', 'adoption-v2-a']
    assert all(row.artifact_ref == _ref('a') for row in rows)
    assert store.read_durable_provenance(after=rows[0].entry.end) == rows[1:]


def test_unknown_cursor_fails_closed_and_effective_tampering_invalidates_cache(tmp_path) -> None:
    store = IncrementalAlarmPersistence(application_root=tmp_path)
    _adopt(store, 'a')
    _commit(store, build_record(commit_id='C1'))
    cursor = store.read_head().durable
    with pytest.raises(ValueError, match='exact durable'):
        store.read_durable_provenance(after=replace(cursor, commit_id='invalid'))
    effective = store.read_effective_head()
    corrupted = effective.as_document()
    corrupted['schema_version'] = 'invalid'
    store._state.replace(store.paths.effective_head_relative, corrupted)
    with pytest.raises(AlarmPersistenceCorruptionError):
        store.read_effective_head()
    with pytest.raises(AlarmPersistenceCorruptionError):
        store.read_effective_head()


def test_restart_revalidates_old_wal_and_rejects_corruption(tmp_path) -> None:
    store = IncrementalAlarmPersistence(application_root=tmp_path)
    _adopt(store, 'a')
    _commit(store, build_record(commit_id='C1'))
    _commit(store, build_record(commit_id='C2', previous_commit_id='C1', cycle_id='second'))
    restarted = IncrementalAlarmPersistence(application_root=tmp_path)
    restarted.recover(assert_authority=_authority, fenced_mutation=mutation_fence)
    assert restarted.read_effective_head().target_artifact_ref == _ref('a')
    path = next((tmp_path / 'alarms' / 'runtime' / 'journal').rglob('part-*.jsonl'))
    payload = path.read_bytes()
    assert b'C1' in payload
    path.write_bytes(payload.replace(b'C1', b'Z1', 1))
    with pytest.raises(AlarmPersistenceCorruptionError):
        IncrementalAlarmPersistence(application_root=tmp_path).recover(
            assert_authority=_authority, fenced_mutation=mutation_fence
        )


def test_interrupted_commit_requires_recovery(tmp_path, monkeypatch) -> None:
    store = IncrementalAlarmPersistence(application_root=tmp_path)
    _adopt(store, 'a')
    _commit(store, build_record(commit_id='C1'))
    original = store._materialize_entry

    def fail(_entry):
        raise RuntimeError('simulated crash after durable head')

    monkeypatch.setattr(store, '_materialize_entry', fail)
    with pytest.raises(RuntimeError, match='simulated crash'):
        _commit(store, build_record(commit_id='C2', previous_commit_id='C1', cycle_id='second'))
    with pytest.raises(AlarmRecoveryRequiredError):
        store.read_effective_head()
    monkeypatch.setattr(store, '_materialize_entry', original)
    store.recover(assert_authority=_authority, fenced_mutation=mutation_fence)
    assert store.read_head().aligned
    assert store.read_snapshot('crusher_pressure').last_commit_id == 'C2'
