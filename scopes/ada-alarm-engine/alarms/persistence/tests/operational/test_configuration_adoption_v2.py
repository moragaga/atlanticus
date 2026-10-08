from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Iterator

import pytest

from ada.alarms.persistence.operational import (
    AlarmArtifactRefSnapshot,
    AlarmPersistence,
    AlarmPersistenceConflictError,
    AlarmPersistenceCorruptionError,
    AlarmPersistenceValidationError,
    AlarmRecoveryRequiredError,
    ConfigurationAdoptionRecord,
    ConfigurationAdoptionRecordV2,
    GroupCommitReference,
)
from ada.alarms.persistence.operational.serialization import (
    build_record_hash,
    decode_record_line,
    encode_record_line,
)

from .support import build_record, mutation_fence


def _authority() -> None:
    return None


def _ref(char: str) -> AlarmArtifactRefSnapshot:
    return AlarmArtifactRefSnapshot(
        source_key='alarm-configuration',
        result_id='alarm-materialization-' + char * 64,
        manifest_sha256=char * 64,
        alarm_configuration_revision='R42',
        confirmed_tool_catalog_revision='T18',
    )


def _groups():
    first = build_record(commit_id='A1', priority_group='a', alarm_key='alarm_a')
    second = build_record(commit_id='B1', priority_group='b', alarm_key='alarm_b')
    return first, second


def _references(records):
    return tuple(
        GroupCommitReference(
            priority_group=record.commit.priority_group,
            commit_id=record.commit.commit_id,
            record_hash=record.record_hash,
        )
        for record in records
    )


def _adoption(records, *, previous=None, target=None, adoption_id='adoption-v2'):
    return ConfigurationAdoptionRecordV2.create(
        adoption_id=adoption_id,
        previous_artifact_ref=previous,
        target_artifact_ref=target or _ref('a'),
        effective_at='2026-08-23T20:00:00Z',
        committed_at='2026-08-23T20:00:00Z',
        group_commits=_references(records),
    )


def _commit(persistence, adoption, groups):
    return persistence.commit_adoption(
        adoption,
        group_records=groups,
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )


def _recover(persistence):
    return persistence.recover(assert_authority=_authority, fenced_mutation=mutation_fence)


def test_v2_roundtrip_records_exact_group_identifiers_and_hashes() -> None:
    groups = _groups()
    record = _adoption(groups)
    assert ConfigurationAdoptionRecordV2.from_document(record.as_document()) == record
    assert record.as_document()['record_schema_version'] == 'configuration-adoption-record.v2'
    assert [ref['priority_group'] for ref in record.as_document()['group_commits']] == ['a', 'b']


def test_v1_record_remains_readable_after_introducing_v2() -> None:
    original = ConfigurationAdoptionRecord.create(
        adoption_id='adoption-v1',
        previous_artifact_ref=None,
        target_artifact_ref=_ref('a'),
        effective_at='2026-08-23T19:00:00Z',
        committed_at='2026-08-23T19:00:00Z',
    )
    assert ConfigurationAdoptionRecord.from_document(original.as_document()) == original


def test_v2_rejects_tampered_group_reference_and_non_canonical_order() -> None:
    groups = _groups()
    record = _adoption(groups)
    document = record.as_document()
    document['group_commits'][0]['record_hash'] = 'sha256:' + '0' * 64
    with pytest.raises(AlarmPersistenceCorruptionError, match='hash'):
        ConfigurationAdoptionRecordV2.from_document(document)
    with pytest.raises(ValueError, match='sorted'):
        _adoption(tuple(reversed(groups)))
    with pytest.raises(ValueError, match='unique'):
        _adoption((groups[0], groups[0]))


def test_v2_requires_exact_record_references_before_wal(tmp_path: Path) -> None:
    persistence = AlarmPersistence(application_root=tmp_path)
    groups = _groups()
    with pytest.raises(AlarmPersistenceValidationError, match='references'):
        _commit(persistence, _adoption(groups), (groups[0],))
    with pytest.raises(AlarmPersistenceValidationError, match='hash'):
        _commit(
            persistence,
            replace(_adoption(groups), record_hash='sha256:' + '0' * 64),
            groups,
        )
    assert persistence.read_head().durable is None
    assert not list(persistence.paths.journal_open_root.rglob('*.jsonl'))


def test_v1_cannot_confirm_group_records(tmp_path: Path) -> None:
    persistence = AlarmPersistence(application_root=tmp_path)
    v1 = ConfigurationAdoptionRecord.create(
        adoption_id='adoption-v1',
        previous_artifact_ref=None,
        target_artifact_ref=_ref('a'),
        effective_at='2026-08-23T20:00:00Z',
        committed_at='2026-08-23T20:00:00Z',
    )
    with pytest.raises(AlarmPersistenceValidationError, match='V1'):
        _commit(persistence, v1, (_groups()[0],))
    assert persistence.read_head().durable is None


def test_first_v2_adoption_confirms_two_groups_with_one_durable_head(tmp_path: Path) -> None:
    persistence = AlarmPersistence(application_root=tmp_path)
    groups = _groups()
    record = _adoption(groups)
    result = _commit(persistence, record, tuple(reversed(groups)))
    assert result.record_count == 3
    assert persistence.read_head().aligned
    assert result.durable.commit_id == record.adoption_id
    assert tuple(entry.record for entry in persistence.read_durable_records()) == groups
    assert tuple(entry.record for entry in persistence.read_durable_adoptions()) == (record,)
    assert persistence.read_snapshot('a') == groups[0].snapshot_after
    assert persistence.read_snapshot('b') == groups[1].snapshot_after
    assert _recover(persistence).applied_count == 0


def test_v1_can_precede_a_v2_adoption_without_changing_v1(tmp_path: Path) -> None:
    persistence = AlarmPersistence(application_root=tmp_path)
    v1 = ConfigurationAdoptionRecord.create(
        adoption_id='adoption-v1',
        previous_artifact_ref=None,
        target_artifact_ref=_ref('a'),
        effective_at='2026-08-23T19:00:00Z',
        committed_at='2026-08-23T19:00:00Z',
    )
    _commit(persistence, v1, ())
    groups = _groups()
    v2 = _adoption(groups, previous=_ref('a'), target=_ref('b'))
    _commit(persistence, v2, groups)
    assert tuple(entry.record for entry in persistence.read_durable_adoptions()) == (v1, v2)
    assert persistence.read_head().aligned


def test_v2_rejects_cross_hour_records_before_wal(tmp_path: Path) -> None:
    persistence = AlarmPersistence(application_root=tmp_path)
    groups = _groups()
    v2 = replace(_adoption(groups), effective_at='2026-08-23T19:00:00Z')
    with pytest.raises(AlarmPersistenceValidationError, match='hash'):
        _commit(persistence, v2, groups)
    v2 = ConfigurationAdoptionRecordV2.create(
        adoption_id='wrong-hour',
        previous_artifact_ref=None,
        target_artifact_ref=_ref('a'),
        effective_at='2026-08-23T21:00:00Z',
        committed_at='2026-08-23T21:00:00Z',
        group_commits=_references(groups),
    )
    with pytest.raises(AlarmPersistenceValidationError, match='UTC hour'):
        _commit(persistence, v2, groups)
    assert persistence.read_head().durable is None


def test_crash_before_durable_discards_entire_unconfirmed_v2_batch(tmp_path: Path) -> None:
    persistence = AlarmPersistence(application_root=tmp_path)
    calls = 0

    @contextmanager
    def fail_before_durable() -> Iterator[None]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('lease lost before durable')
        yield

    groups = _groups()
    with pytest.raises(RuntimeError, match='before durable'):
        persistence.commit_adoption(
            _adoption(groups),
            group_records=groups,
            assert_authority=_authority,
            fenced_mutation=fail_before_durable,
        )
    assert persistence.read_head().durable is None
    assert persistence.list_snapshots() == ()
    result = _recover(persistence)
    assert result.discarded_tail_bytes > 0
    assert persistence.read_durable_records() == ()
    assert persistence.read_durable_adoptions() == ()


def test_crash_after_durable_before_snapshots_replays_all_three_records(
    tmp_path: Path, monkeypatch
) -> None:
    persistence = AlarmPersistence(application_root=tmp_path)
    groups = _groups()
    record = _adoption(groups)
    original = persistence._materialize_entry

    def fail(entry):
        raise RuntimeError('crash after durable')

    monkeypatch.setattr(persistence, '_materialize_entry', fail)
    with pytest.raises(RuntimeError, match='after durable'):
        _commit(persistence, record, groups)
    monkeypatch.setattr(persistence, '_materialize_entry', original)
    assert persistence.read_head().durable is not None
    assert persistence.read_head().materialized is None
    with pytest.raises(AlarmRecoveryRequiredError):
        _commit(persistence, record, groups)
    first = _recover(persistence)
    second = _recover(persistence)
    assert first.applied_count == 3
    assert second.applied_count == 0
    assert persistence.read_head().aligned
    assert persistence.read_snapshot('a') == groups[0].snapshot_after
    assert persistence.read_snapshot('b') == groups[1].snapshot_after


def test_crash_during_second_snapshot_keeps_materialized_head_before_v2_batch(
    tmp_path: Path, monkeypatch
) -> None:
    persistence = AlarmPersistence(application_root=tmp_path)
    groups = _groups()
    record = _adoption(groups)
    original = persistence._materialize_entry
    calls = 0

    def fail_second_group(entry):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('crash during second group')
        return original(entry)

    monkeypatch.setattr(persistence, '_materialize_entry', fail_second_group)
    with pytest.raises(RuntimeError, match='second group'):
        _commit(persistence, record, groups)
    monkeypatch.setattr(persistence, '_materialize_entry', original)
    assert persistence.read_snapshot('a') == groups[0].snapshot_after
    assert persistence.read_snapshot('b') is None
    assert persistence.read_head().materialized is None
    first = _recover(persistence)
    assert first.applied_count == 2
    assert first.skipped_count == 1
    assert persistence.read_head().aligned
    assert tuple(entry.record for entry in persistence.read_durable_adoptions()) == (record,)


def test_crash_during_recovery_never_publishes_partial_v2_materialized_head(
    tmp_path: Path, monkeypatch
) -> None:
    persistence = AlarmPersistence(application_root=tmp_path)
    groups = _groups()
    record = _adoption(groups)
    original = persistence._materialize_entry
    monkeypatch.setattr(
        persistence,
        '_materialize_entry',
        lambda entry: (_ for _ in ()).throw(RuntimeError('first crash')),
    )
    with pytest.raises(RuntimeError, match='first crash'):
        _commit(persistence, record, groups)
    calls = 0

    def fail_recovery(entry):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('second crash')
        return original(entry)

    monkeypatch.setattr(persistence, '_materialize_entry', fail_recovery)
    with pytest.raises(RuntimeError, match='second crash'):
        _recover(persistence)
    assert persistence.read_head().materialized is None
    monkeypatch.setattr(persistence, '_materialize_entry', original)
    assert _recover(persistence).applied_count == 2
    assert persistence.read_head().aligned


def test_stale_previous_artifact_and_legacy_first_v2_fail_closed(tmp_path: Path) -> None:
    persistence = AlarmPersistence(application_root=tmp_path)
    groups = _groups()
    _commit(persistence, _adoption(groups), groups)
    second = _groups()
    with pytest.raises(AlarmPersistenceConflictError, match='previous artifact'):
        _commit(persistence, _adoption(second, adoption_id='stale', target=_ref('b')), second)
    legacy = AlarmPersistence(application_root=tmp_path / 'legacy')
    legacy.commit_batch(groups, assert_authority=_authority, fenced_mutation=mutation_fence)
    with pytest.raises(AlarmPersistenceConflictError, match='legacy'):
        _commit(legacy, _adoption(groups), groups)


def test_corrupt_durable_v2_group_reference_fails_recovery(tmp_path: Path) -> None:
    persistence = AlarmPersistence(application_root=tmp_path)
    groups = _groups()
    _commit(persistence, _adoption(groups), groups)
    segment = next(persistence.paths.journal_open_root.rglob('*.jsonl'))
    data = segment.read_bytes()
    segment.write_bytes(data.replace(b'"adoption-v2"', b'"adoption-vX"'))
    with pytest.raises(AlarmPersistenceCorruptionError):
        _recover(persistence)


def test_ordinary_group_batch_still_recovers_per_record(tmp_path: Path, monkeypatch) -> None:
    persistence = AlarmPersistence(application_root=tmp_path)
    record = build_record()
    original = persistence._materialize_entry
    monkeypatch.setattr(
        persistence,
        '_materialize_entry',
        lambda entry: (_ for _ in ()).throw(RuntimeError('ordinary crash')),
    )
    with pytest.raises(RuntimeError, match='ordinary crash'):
        persistence.commit_batch(
            (record,), assert_authority=_authority, fenced_mutation=mutation_fence
        )
    monkeypatch.setattr(persistence, '_materialize_entry', original)
    assert _recover(persistence).applied_count == 1
    assert persistence.read_head().aligned


def test_altered_group_payload_with_valid_group_hash_breaks_v2_reference(tmp_path: Path) -> None:
    persistence = AlarmPersistence(application_root=tmp_path)
    groups = _groups()
    _commit(persistence, _adoption(groups), groups)
    segment = next(persistence.paths.journal_open_root.rglob('*.jsonl'))
    lines = segment.read_bytes().splitlines(keepends=True)
    assert len(lines) == 3
    document = decode_record_line(lines[0])
    document['records']['journey_events'][0]['journey_event_id'] = 'J-Q1'
    document['record_hash'] = build_record_hash(
        {name: value for name, value in document.items() if name != 'record_hash'}
    )
    replacement = encode_record_line(document)
    assert len(replacement) == len(lines[0])
    segment.write_bytes(replacement + b''.join(lines[1:]))
    with pytest.raises(AlarmPersistenceCorruptionError, match='references'):
        _recover(persistence)


def test_in_memory_corrupt_group_record_is_rejected_before_any_wal_write(tmp_path: Path) -> None:
    persistence = AlarmPersistence(application_root=tmp_path)
    groups = _groups()
    altered = replace(groups[0], record_hash='sha256:' + '0' * 64)
    with pytest.raises(AlarmPersistenceValidationError, match='group commit record hash'):
        persistence.commit_adoption(
            _adoption((altered, groups[1])),
            group_records=(altered, groups[1]),
            assert_authority=_authority,
            fenced_mutation=mutation_fence,
        )
    assert persistence.read_head().durable is None


def test_group_revision_must_match_the_exact_target_artifact(tmp_path: Path) -> None:
    persistence = AlarmPersistence(application_root=tmp_path)
    groups = _groups()
    target = AlarmArtifactRefSnapshot(
        source_key='alarm-configuration',
        result_id='alarm-materialization-' + 'c' * 64,
        manifest_sha256='d' * 64,
        alarm_configuration_revision='R43',
        confirmed_tool_catalog_revision='T18',
    )
    adoption = _adoption(groups, target=target)
    with pytest.raises(AlarmPersistenceValidationError, match='revisions must match target'):
        _commit(persistence, adoption, groups)
    assert persistence.read_head().durable is None
