from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Iterator

import pytest

from ada_command_center.alarms.persistence import (
    AlarmArtifactRefSnapshot,
    AlarmPersistence,
    AlarmPersistenceConflictError,
    AlarmPersistenceCorruptionError,
    AlarmPersistenceValidationError,
    AlarmRecoveryRequiredError,
    ConfigurationAdoptionRecord,
)
from tests.support import build_record, mutation_fence


def _authority() -> None:
    return None


def _pin(char: str) -> AlarmArtifactRefSnapshot:
    return AlarmArtifactRefSnapshot(
        source_key='alarm-configuration',
        result_id='alarm-materialization-' + char * 64,
        manifest_sha256=char * 64,
        alarm_configuration_revision='R42',
        confirmed_tool_catalog_revision='T18',
    )


def _adoption(
    *,
    adoption_id: str = 'adoption-1',
    previous: AlarmArtifactRefSnapshot | None = None,
    target: AlarmArtifactRefSnapshot | None = None,
    effective_at: str = '2026-08-23T19:00:00Z',
) -> ConfigurationAdoptionRecord:
    return ConfigurationAdoptionRecord.create(
        adoption_id=adoption_id,
        previous_artifact_ref=previous,
        target_artifact_ref=target or _pin('a'),
        effective_at=effective_at,
        committed_at=effective_at,
    )


def test_adoption_record_roundtrip_preserves_exact_artifact_and_hash() -> None:
    original = _adoption()
    decoded = ConfigurationAdoptionRecord.from_document(original.as_document())
    assert decoded == original
    assert decoded.target_artifact_ref.as_document()['resolution_key'] == {
        'alarm_configuration_revision': 'R42',
        'confirmed_tool_catalog_revision': 'T18',
    }


@pytest.mark.parametrize('field', ['result_id', 'manifest_sha256', 'resolution_key'])
def test_adoption_record_fails_closed_on_corrupt_exact_identity(field: str) -> None:
    document = _adoption().as_document()
    document['target_artifact_ref'][field] = 'invalid'
    with pytest.raises(AlarmPersistenceCorruptionError):
        ConfigurationAdoptionRecord.from_document(document)


def test_adoption_record_fails_closed_on_changed_payload_and_unknown_fields() -> None:
    document = _adoption().as_document()
    document['adoption_id'] = 'tampered-adoption-id'
    with pytest.raises(AlarmPersistenceCorruptionError, match='hash'):
        ConfigurationAdoptionRecord.from_document(document)
    document = _adoption().as_document()
    document['unexpected'] = True
    with pytest.raises(AlarmPersistenceCorruptionError, match='fields'):
        ConfigurationAdoptionRecord.from_document(document)


def test_adoption_record_rejects_equal_artifact_and_non_utc_time() -> None:
    with pytest.raises(ValueError, match='result_id'):
        _adoption(previous=_pin('a'))
    with pytest.raises(ValueError, match='UTC'):
        _adoption(effective_at='2026-08-23T19:00:00')


def test_adoption_rejects_invalid_in_memory_hash_before_wal(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    record = replace(_adoption(), record_hash='sha256:' + '0' * 64)
    with pytest.raises(AlarmPersistenceValidationError, match='hash'):
        persistence.commit_adoption(
            record, assert_authority=_authority, fenced_mutation=mutation_fence
        )
    assert persistence.read_head().durable is None
    assert not list(persistence.paths.journal_open_root.rglob('*.jsonl'))


def test_zero_group_adoption_is_durable_without_group_snapshots(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    record = _adoption()
    result = persistence.commit_adoption(
        record, assert_authority=_authority, fenced_mutation=mutation_fence
    )
    assert result.record_count == 1
    assert result.durable == result.materialized
    assert persistence.read_head().aligned
    assert persistence.list_snapshots() == ()
    assert persistence.read_durable_records() == ()
    assert tuple(entry.record for entry in persistence.read_durable_adoptions()) == (record,)
    assert (
        persistence.recover(
            assert_authority=_authority, fenced_mutation=mutation_fence
        ).applied_count
        == 0
    )


def test_crash_before_durable_discards_unconfirmed_adoption(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    calls = 0

    @contextmanager
    def fail_before_durable() -> Iterator[None]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('lease lost')
        yield

    with pytest.raises(RuntimeError, match='lease lost'):
        persistence.commit_adoption(
            _adoption(), assert_authority=_authority, fenced_mutation=fail_before_durable
        )
    assert persistence.read_head().durable is None
    assert (
        persistence.recover(
            assert_authority=_authority, fenced_mutation=mutation_fence
        ).discarded_tail_bytes
        > 0
    )
    assert persistence.read_durable_adoptions() == ()


def test_crash_after_durable_replays_adoption_once(tmp_path: Path, monkeypatch) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    record = _adoption()
    materialize = persistence._materialize_entry
    monkeypatch.setattr(
        persistence,
        '_materialize_entry',
        lambda entry: (_ for _ in ()).throw(RuntimeError('crash after durable')),
    )
    with pytest.raises(RuntimeError, match='crash after durable'):
        persistence.commit_adoption(
            record, assert_authority=_authority, fenced_mutation=mutation_fence
        )
    monkeypatch.setattr(persistence, '_materialize_entry', materialize)
    assert persistence.read_head().durable is not None
    assert not persistence.read_head().aligned
    assert tuple(entry.record for entry in persistence.read_durable_adoptions()) == (record,)
    with pytest.raises(AlarmRecoveryRequiredError):
        persistence.commit_adoption(
            _adoption(adoption_id='adoption-retry'),
            assert_authority=_authority,
            fenced_mutation=mutation_fence,
        )
    first = persistence.recover(assert_authority=_authority, fenced_mutation=mutation_fence)
    second = persistence.recover(assert_authority=_authority, fenced_mutation=mutation_fence)
    assert first.applied_count == 1
    assert second.applied_count == 0
    assert persistence.read_head().aligned
    assert tuple(entry.record for entry in persistence.read_durable_adoptions()) == (record,)


def test_durable_adoption_chain_rejects_stale_previous_and_duplicate_id(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    first = _adoption()
    persistence.commit_adoption(first, assert_authority=_authority, fenced_mutation=mutation_fence)
    with pytest.raises(AlarmPersistenceConflictError, match='previous artifact'):
        persistence.commit_adoption(
            _adoption(adoption_id='stale', target=_pin('b')),
            assert_authority=_authority,
            fenced_mutation=mutation_fence,
        )
    with pytest.raises(AlarmPersistenceConflictError, match='adoption_id'):
        persistence.commit_adoption(
            _adoption(adoption_id='adoption-1', previous=_pin('a'), target=_pin('b')),
            assert_authority=_authority,
            fenced_mutation=mutation_fence,
        )
    second = _adoption(adoption_id='adoption-2', previous=_pin('a'), target=_pin('b'))
    persistence.commit_adoption(second, assert_authority=_authority, fenced_mutation=mutation_fence)
    assert tuple(entry.record for entry in persistence.read_durable_adoptions()) == (first, second)


def test_ordinary_group_commits_keep_their_existing_read_contract(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    adoption = _adoption()
    persistence.commit_adoption(
        adoption, assert_authority=_authority, fenced_mutation=mutation_fence
    )
    ordinary = build_record()
    persistence.commit_batch(
        (ordinary,), assert_authority=_authority, fenced_mutation=mutation_fence
    )
    assert tuple(entry.record for entry in persistence.read_durable_records()) == (ordinary,)
    assert tuple(entry.record for entry in persistence.read_durable_adoptions()) == (adoption,)
    assert persistence.read_snapshot('crusher_pressure') == ordinary.snapshot_after
    assert (
        persistence.recover(
            assert_authority=_authority, fenced_mutation=mutation_fence
        ).applied_count
        == 0
    )


def test_first_adoption_rejects_unmigrated_durable_group_history(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    persistence.commit_batch(
        (build_record(),), assert_authority=_authority, fenced_mutation=mutation_fence
    )
    with pytest.raises(AlarmPersistenceConflictError, match='legacy state migration'):
        persistence.commit_adoption(
            _adoption(effective_at='2026-08-23T21:00:00Z'),
            assert_authority=_authority,
            fenced_mutation=mutation_fence,
        )


def test_corrupt_durable_adoption_fails_recovery(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    persistence.commit_adoption(
        _adoption(), assert_authority=_authority, fenced_mutation=mutation_fence
    )
    segment = next(persistence.paths.journal_open_root.rglob('*.jsonl'))
    original = segment.read_bytes()
    segment.write_bytes(original.replace(b'"adoption-1"', b'"adoption-2"'))
    with pytest.raises(AlarmPersistenceCorruptionError):
        persistence.recover(assert_authority=_authority, fenced_mutation=mutation_fence)
