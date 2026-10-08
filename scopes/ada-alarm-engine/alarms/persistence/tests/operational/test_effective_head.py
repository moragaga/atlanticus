from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Iterator

import pytest

from ada.alarms.persistence.operational import (
    ALARM_EFFECTIVE_HEAD_SCHEMA_VERSION,
    AlarmArtifactRefSnapshot,
    AlarmEffectiveConfigurationHead,
    AlarmPersistence,
    AlarmPersistenceCorruptionError,
    AlarmRecoveryRequiredError,
    ConfigurationAdoptionRecord,
    ConfigurationAdoptionRecordV2,
    GroupCommitReference,
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


def _v1(
    *,
    adoption_id: str = 'adoption-v1',
    previous: AlarmArtifactRefSnapshot | None = None,
    target: AlarmArtifactRefSnapshot | None = None,
    effective_at: str = '2026-08-23T19:00:00Z',
) -> ConfigurationAdoptionRecord:
    return ConfigurationAdoptionRecord.create(
        adoption_id=adoption_id,
        previous_artifact_ref=previous,
        target_artifact_ref=target or _ref('a'),
        effective_at=effective_at,
        committed_at=effective_at,
    )


def _groups():
    return (
        build_record(commit_id='A1', priority_group='a', alarm_key='alarm_a'),
        build_record(commit_id='B1', priority_group='b', alarm_key='alarm_b'),
    )


def _v2(
    groups,
    *,
    previous: AlarmArtifactRefSnapshot | None = None,
    target: AlarmArtifactRefSnapshot | None = None,
) -> ConfigurationAdoptionRecordV2:
    return ConfigurationAdoptionRecordV2.create(
        adoption_id='adoption-v2',
        previous_artifact_ref=previous,
        target_artifact_ref=target or _ref('b'),
        effective_at='2026-08-23T20:00:00Z',
        committed_at='2026-08-23T20:00:00Z',
        group_commits=tuple(
            GroupCommitReference(
                priority_group=record.commit.priority_group,
                commit_id=record.commit.commit_id,
                record_hash=record.record_hash,
            )
            for record in groups
        ),
    )


def _commit(persistence: AlarmPersistence, adoption, groups=()):
    return persistence.commit_adoption(
        adoption,
        group_records=groups,
        assert_authority=_authority,
        fenced_mutation=mutation_fence,
    )


def _recover(persistence: AlarmPersistence):
    return persistence.recover(assert_authority=_authority, fenced_mutation=mutation_fence)


def _path(persistence: AlarmPersistence) -> Path:
    return persistence.paths.alarms_root / persistence.paths.effective_head_relative


def test_no_adoption_has_no_effective_head(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    assert persistence.read_effective_head() is None
    assert not _path(persistence).exists()
    assert _recover(persistence).applied_count == 0
    assert persistence.read_effective_head() is None


def test_v1_publishes_exact_effective_head_without_group_snapshots(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    adoption = _v1()
    result = _commit(persistence, adoption)
    expected = AlarmEffectiveConfigurationHead.from_adoption_entry(
        persistence.read_durable_adoptions()[-1]
    )
    assert persistence.read_effective_head() == expected
    assert expected.adoption_position == result.durable
    assert expected.adoption_record_hash == adoption.record_hash
    assert expected.target_artifact_ref == _ref('a')
    assert persistence.list_snapshots() == ()
    assert _path(persistence).exists()
    assert _recover(persistence).applied_count == 0


def test_effective_document_roundtrip_and_strict_schema(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _commit(persistence, _v1())
    original = persistence.read_effective_head()
    assert original is not None
    payload = original.as_document()
    assert payload['schema_version'] == ALARM_EFFECTIVE_HEAD_SCHEMA_VERSION
    assert AlarmEffectiveConfigurationHead.from_document(payload) == original
    payload['unexpected'] = True
    with pytest.raises(AlarmPersistenceCorruptionError, match='fields'):
        AlarmEffectiveConfigurationHead.from_document(payload)
    payload = original.as_document()
    payload['adoption_position']['commit_id'] = 'other'
    with pytest.raises(AlarmPersistenceCorruptionError):
        AlarmEffectiveConfigurationHead.from_document(payload)
    payload = original.as_document()
    payload['schema_version'] = 'unsupported'
    with pytest.raises(AlarmPersistenceCorruptionError, match='schema'):
        AlarmEffectiveConfigurationHead.from_document(payload)


def test_v1_and_v2_choose_latest_exact_artifact_even_when_revisions_match(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _commit(persistence, _v1())
    first = persistence.read_effective_head()
    groups = _groups()
    adoption = _v2(groups, previous=_ref('a'))
    _commit(persistence, adoption, groups)
    last = persistence.read_effective_head()
    assert first is not None and last is not None
    assert last.target_artifact_ref == _ref('b')
    assert (
        first.target_artifact_ref.alarm_configuration_revision
        == last.target_artifact_ref.alarm_configuration_revision
    )
    assert last.adoption_record_hash == adoption.record_hash
    assert last.adoption_position.commit_id == adoption.adoption_id
    assert _recover(persistence).applied_count == 0
    assert persistence.read_effective_head() == last


def test_v2_initial_publishes_only_after_both_group_snapshots(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    groups = _groups()
    _commit(persistence, _v2(groups), groups)
    effective = persistence.read_effective_head()
    assert effective is not None
    assert effective.target_artifact_ref == _ref('b')
    assert persistence.read_snapshot('a') == groups[0].snapshot_after
    assert persistence.read_snapshot('b') == groups[1].snapshot_after


def test_unaligned_v2_never_exposes_new_effective(tmp_path: Path, monkeypatch) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    groups = _groups()
    original = persistence._materialize_entry
    calls = 0

    def fail_second(entry):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('crash during second group')
        return original(entry)

    monkeypatch.setattr(persistence, '_materialize_entry', fail_second)
    with pytest.raises(RuntimeError, match='second group'):
        _commit(persistence, _v2(groups), groups)
    assert not persistence.read_head().aligned
    assert not _path(persistence).exists()
    with pytest.raises(AlarmRecoveryRequiredError, match='recovered'):
        persistence.read_effective_head()
    monkeypatch.setattr(persistence, '_materialize_entry', original)
    _recover(persistence)
    assert persistence.read_effective_head() is not None


def test_crash_after_materialized_before_effective_recovers_without_replay(
    tmp_path: Path, monkeypatch
) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    original = persistence._write_effective_head
    monkeypatch.setattr(
        persistence,
        '_write_effective_head',
        lambda head: (_ for _ in ()).throw(RuntimeError('effective publication crash')),
    )
    with pytest.raises(RuntimeError, match='effective publication crash'):
        _commit(persistence, _v1())
    assert persistence.read_head().aligned
    assert not _path(persistence).exists()
    with pytest.raises(AlarmRecoveryRequiredError, match='requires recovery'):
        persistence.read_effective_head()
    monkeypatch.setattr(persistence, '_write_effective_head', original)
    assert _recover(persistence).applied_count == 0
    assert persistence.read_effective_head() is not None
    assert _recover(persistence).applied_count == 0


def test_fencing_before_effective_publication_prevents_unfenced_write(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    calls = 0

    @contextmanager
    def fenced() -> Iterator[None]:
        nonlocal calls
        calls += 1
        if calls == 5:
            raise RuntimeError('lease lost before effective publication')
        yield

    with pytest.raises(RuntimeError, match='lease lost'):
        persistence.commit_adoption(_v1(), assert_authority=_authority, fenced_mutation=fenced)
    assert persistence.read_head().aligned
    assert not _path(persistence).exists()
    with pytest.raises(AlarmRecoveryRequiredError):
        persistence.read_effective_head()
    _recover(persistence)
    assert persistence.read_effective_head() is not None


def test_missing_projection_is_not_silently_replaced_on_read(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _commit(persistence, _v1())
    _path(persistence).unlink()
    restarted = AlarmPersistence(shared_volume_path=tmp_path)
    with pytest.raises(AlarmRecoveryRequiredError):
        restarted.read_effective_head()
    assert not _path(restarted).exists()
    _recover(restarted)
    assert restarted.read_effective_head() is not None


def test_corrupt_projection_fails_read_and_recovery_repairs_from_verified_wal(
    tmp_path: Path,
) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _commit(persistence, _v1())
    payload = persistence.read_effective_head().as_document()
    payload['schema_version'] = 'corrupted'
    persistence._state.replace(persistence.paths.effective_head_relative, payload)
    with pytest.raises(AlarmPersistenceCorruptionError, match='schema'):
        persistence.read_effective_head()
    _recover(persistence)
    assert persistence.read_effective_head().adoption_id == 'adoption-v1'


def test_stale_projection_requires_recovery_and_rebuilds_latest_from_wal(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _commit(persistence, _v1())
    old = persistence.read_effective_head()
    _commit(
        persistence,
        _v1(
            adoption_id='adoption-next',
            previous=_ref('a'),
            target=_ref('b'),
            effective_at='2026-08-23T20:00:00Z',
        ),
    )
    persistence._state.replace(persistence.paths.effective_head_relative, old.as_document())
    with pytest.raises(AlarmRecoveryRequiredError):
        persistence.read_effective_head()
    _recover(persistence)
    assert persistence.read_effective_head().adoption_id == 'adoption-next'


def test_snapshot_content_divergence_blocks_effective_and_recovery(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    groups = _groups()
    _commit(persistence, _v2(groups), groups)
    changed = build_record(
        commit_id='A1', priority_group='a', alarm_key='alarm_a', error_key='altered'
    )
    assert changed.snapshot_after != groups[0].snapshot_after
    persistence._state.replace(
        persistence.paths.group_snapshot_relative('a'), changed.snapshot_after.as_document()
    )
    with pytest.raises(AlarmPersistenceCorruptionError, match='snapshots'):
        persistence.read_effective_head()
    with pytest.raises(AlarmPersistenceCorruptionError, match='snapshots'):
        _recover(persistence)


def test_orphan_snapshot_blocks_effective_publication(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _commit(persistence, _v1())
    persistence._state.replace(
        persistence.paths.group_snapshot_relative('orphan'),
        build_record(
            priority_group='orphan', alarm_key='alarm_orphan'
        ).snapshot_after.as_document(),
    )
    with pytest.raises(AlarmPersistenceCorruptionError, match='snapshots'):
        persistence.read_effective_head()
    with pytest.raises(AlarmPersistenceCorruptionError, match='snapshots'):
        _recover(persistence)


def test_physical_effective_without_durable_wal_fails_closed(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _commit(persistence, _v1())
    payload = persistence.read_effective_head().as_document()
    orphan = AlarmPersistence(shared_volume_path=tmp_path / 'orphan')
    orphan._state.replace(orphan.paths.effective_head_relative, payload)
    with pytest.raises(AlarmPersistenceCorruptionError, match='without a durable'):
        orphan.read_effective_head()
    with pytest.raises(AlarmPersistenceCorruptionError, match='without a durable'):
        _recover(orphan)


def test_ordinary_group_commit_does_not_change_effective_identity(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _commit(persistence, _v1())
    old = persistence.read_effective_head()
    record = build_record()
    persistence.commit_batch((record,), assert_authority=_authority, fenced_mutation=mutation_fence)
    assert persistence.read_effective_head() == old
    _recover(persistence)
    assert persistence.read_effective_head() == old


def test_legacy_group_history_does_not_invent_effective(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    persistence.commit_batch(
        (build_record(),), assert_authority=_authority, fenced_mutation=mutation_fence
    )
    assert persistence.read_effective_head() is None
    assert not _path(persistence).exists()
    assert _recover(persistence).applied_count == 0
    assert persistence.read_effective_head() is None


def test_in_memory_head_requires_exact_artifact_and_record_position(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _commit(persistence, _v1())
    head = persistence.read_effective_head()
    with pytest.raises(ValueError, match='adoption_position'):
        replace(head, adoption_id='different')
    with pytest.raises(ValueError, match='hash'):
        replace(head, adoption_record_hash='incorrect')
    with pytest.raises(ValueError, match='UTC'):
        replace(head, effective_at='2026-08-23T19:00:00')


def test_corrupt_wal_cannot_be_repaired_from_effective_projection(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _commit(persistence, _v1())
    segment = next(persistence.paths.journal_open_root.rglob('*.jsonl'))
    content = segment.read_bytes()
    assert b'adoption-v1' in content
    segment.write_bytes(content.replace(b'adoption-v1', b'adoption-vX'))
    with pytest.raises(AlarmPersistenceCorruptionError):
        persistence.read_effective_head()
    with pytest.raises(AlarmPersistenceCorruptionError):
        _recover(persistence)


def test_v2_aligned_crash_before_projection_repairs_without_snapshot_replay(
    tmp_path: Path, monkeypatch
) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    groups = _groups()
    original = persistence._write_effective_head
    monkeypatch.setattr(
        persistence,
        '_write_effective_head',
        lambda head: (_ for _ in ()).throw(RuntimeError('V2 projection failure')),
    )
    with pytest.raises(RuntimeError, match='V2 projection failure'):
        _commit(persistence, _v2(groups), groups)
    assert persistence.read_head().aligned
    assert persistence.read_snapshot('a') == groups[0].snapshot_after
    assert persistence.read_snapshot('b') == groups[1].snapshot_after
    with pytest.raises(AlarmRecoveryRequiredError):
        persistence.read_effective_head()
    monkeypatch.setattr(persistence, '_write_effective_head', original)
    assert _recover(persistence).applied_count == 0
    assert persistence.read_effective_head().adoption_id == 'adoption-v2'
