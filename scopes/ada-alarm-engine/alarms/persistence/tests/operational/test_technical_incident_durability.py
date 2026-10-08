from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ada.alarms.core import (
    AlarmEvaluation,
    AlarmStatus,
    EvaluationError,
    EvaluationErrorOrigin,
    EvidenceSnapshot,
    reduce_initial_technical_incidents,
)
from ada.alarms.persistence.operational import (
    ENGINE_COMMIT_RECORD_V2_SCHEMA_VERSION,
    GROUP_RUNTIME_SNAPSHOT_V2_SCHEMA_VERSION,
    AlarmPersistence,
    AlarmPersistenceCorruptionError,
    AlarmPersistenceValidationError,
    EngineCommitMetadata,
    EngineCommitRecord,
    GroupRuntimeSnapshot,
    build_technical_incident_commit,
    read_open_technical_incidents,
    snapshot_technical_incidents,
)
from ada.contracts.alarms import AlarmIdentity

from .support import build_record

AT = datetime(2026, 10, 8, 11, 0, tzinfo=UTC)
IDENTITY = AlarmIdentity(family_key='mill', alarm_key='risk')
GROUP = 'crusher_pressure'


@contextmanager
def _fence():
    yield


def _authority() -> None:
    return None


def _evaluation(*, at: datetime, error_key: str | None = 'a') -> AlarmEvaluation:
    if error_key is None:
        return AlarmEvaluation(
            alarm_identity=IDENTITY,
            status=AlarmStatus.INACTIVE,
            evaluated_at=at,
            evidence_snapshot=EvidenceSnapshot(
                contract_key='test', contract_version='v1', payload={}
            ),
        )
    return AlarmEvaluation(
        alarm_identity=IDENTITY,
        status=AlarmStatus.ERROR,
        evaluated_at=at,
        error=EvaluationError(
            origin=EvaluationErrorOrigin.QUALITY,
            error_key=error_key,
            message=f'Error {error_key}',
        ),
    )


def _reduce(prior, *, at: datetime, error_key: str | None = 'a'):
    return reduce_initial_technical_incidents(
        prior,
        evaluations=(_evaluation(at=at, error_key=error_key),),
        executable_groups={IDENTITY: GROUP},
        cycle_at=at,
    )


def _metadata(*, at: datetime, commit_id: str, previous: str | None) -> EngineCommitMetadata:
    return EngineCommitMetadata(
        commit_id=commit_id,
        cycle_id=f'cycle-{commit_id}',
        priority_group=GROUP,
        previous_commit_id=previous,
        evaluated_at=at.isoformat().replace('+00:00', 'Z'),
        committed_at=at.isoformat().replace('+00:00', 'Z'),
        alarm_configuration_revision='R42',
        tool_registry_revision='T18',
        runtime_artifact_version='ada-alarms-runtime-test',
        affected_alarms=(IDENTITY.canonical_key,),
    )


def _base(commit_id: str) -> GroupRuntimeSnapshot:
    return GroupRuntimeSnapshot(
        {
            'snapshot_schema_version': 'group-runtime-snapshot.v1',
            'priority_group': GROUP,
            'last_commit_id': commit_id,
            'alarms': {},
        }
    )


def _commit(
    prior_snapshot, prior_incidents, *, at: datetime, error_key: str | None, commit_id: str
):
    result = _reduce(prior_incidents, at=at, error_key=error_key)
    previous_id = None if prior_snapshot is None else prior_snapshot.last_commit_id
    record = build_technical_incident_commit(
        commit=_metadata(at=at, commit_id=commit_id, previous=previous_id),
        snapshot_after=_base(commit_id),
        previous_snapshot=prior_snapshot,
        open_incidents=result.open_incidents,
        changes=result.changes,
    )
    return result, record


def _persist(persistence, record):
    return persistence.commit_batch([record], assert_authority=_authority, fenced_mutation=_fence)


def test_start_is_a_v2_commit_in_same_wal_and_recovers_open_incident(tmp_path: Path):
    store = AlarmPersistence(application_root=tmp_path)
    reduction, record = _commit(None, (), at=AT, error_key='a', commit_id='C1')
    assert record is not None
    assert record.as_document()['record_schema_version'] == ENGINE_COMMIT_RECORD_V2_SCHEMA_VERSION
    assert (
        record.snapshot_after.as_document()['snapshot_schema_version']
        == GROUP_RUNTIME_SNAPSHOT_V2_SCHEMA_VERSION
    )
    _persist(store, record)

    restarted = AlarmPersistence(application_root=tmp_path)
    restarted.recover(assert_authority=_authority, fenced_mutation=_fence)
    assert read_open_technical_incidents(restarted) == reduction.open_incidents
    assert restarted.read_durable_records()[0].record == record


def test_1200_repeated_errors_do_not_append_more_wal_records(tmp_path: Path):
    store = AlarmPersistence(application_root=tmp_path)
    first, record = _commit(None, (), at=AT, error_key='a', commit_id='C1')
    assert record is not None
    _persist(store, record)
    previous_snapshot = store.read_snapshot(GROUP)
    prior_incidents = first.open_incidents
    for index in range(1, 1201):
        at = AT + timedelta(seconds=index * 3)
        next_state, repeated = _commit(
            previous_snapshot,
            prior_incidents,
            at=at,
            error_key='a',
            commit_id=f'C{index + 1}',
        )
        assert repeated is None
        prior_incidents = next_state.open_incidents
    assert len(store.read_durable_records()) == 1
    assert read_open_technical_incidents(store) == first.open_incidents


def test_changed_and_resolved_are_only_new_durable_transitions(tmp_path: Path):
    store = AlarmPersistence(application_root=tmp_path)
    previous = ()
    prior_snapshot = None
    for n, (error_key, kind) in enumerate(
        (('a', 'STARTED'), ('b', 'CHANGED'), ('a', 'CHANGED'), (None, 'RESOLVED')),
        start=1,
    ):
        result, record = _commit(
            prior_snapshot,
            previous,
            at=AT + timedelta(seconds=(n - 1) * 3),
            error_key=error_key,
            commit_id=f'C{n}',
        )
        assert record is not None
        assert record.records['technical_incident_changes'][0]['kind'] == kind
        _persist(store, record)
        previous = result.open_incidents
        prior_snapshot = store.read_snapshot(GROUP)
    assert read_open_technical_incidents(AlarmPersistence(application_root=tmp_path)) == ()
    assert len(store.read_durable_records()) == 4


def test_recovery_after_durable_head_restores_incident_once(tmp_path: Path, monkeypatch):
    store = AlarmPersistence(application_root=tmp_path)
    result, record = _commit(None, (), at=AT, error_key='a', commit_id='C1')
    assert record is not None
    original = store._materialize_entry

    def fail(_entry):
        raise RuntimeError('simulated crash')

    monkeypatch.setattr(store, '_materialize_entry', fail)
    with pytest.raises(RuntimeError, match='simulated crash'):
        _persist(store, record)
    monkeypatch.setattr(store, '_materialize_entry', original)
    restart = AlarmPersistence(application_root=tmp_path)
    restart.recover(assert_authority=_authority, fenced_mutation=_fence)
    assert read_open_technical_incidents(restart) == result.open_incidents
    unchanged = _reduce(
        read_open_technical_incidents(restart),
        at=AT + timedelta(seconds=3),
        error_key='a',
    )
    assert unchanged.changes == ()
    assert len(restart.read_durable_records()) == 1


def test_unconfirmed_wal_tail_does_not_restore_incident(tmp_path: Path, monkeypatch):
    store = AlarmPersistence(application_root=tmp_path)
    _, record = _commit(None, (), at=AT, error_key='a', commit_id='C1')
    assert record is not None
    original = store._replace_head

    def fail(_head):
        raise RuntimeError('crash before durable head')

    monkeypatch.setattr(store, '_replace_head', fail)
    with pytest.raises(RuntimeError, match='crash before durable head'):
        _persist(store, record)
    monkeypatch.setattr(store, '_replace_head', original)
    restart = AlarmPersistence(application_root=tmp_path)
    outcome = restart.recover(assert_authority=_authority, fenced_mutation=_fence)
    assert outcome.discarded_tail_bytes > 0
    assert read_open_technical_incidents(restart) == ()
    assert restart.read_durable_records() == ()


def test_v1_snapshot_remains_readable_and_v2_preserves_physical_alarms(tmp_path: Path):
    store = AlarmPersistence(application_root=tmp_path)
    original = build_record(priority_group=GROUP, commit_id='C0')
    _persist(store, original)
    old_snapshot = store.read_snapshot(GROUP)
    assert old_snapshot == original.snapshot_after
    assert snapshot_technical_incidents(old_snapshot) == ()
    reduced = _reduce((), at=AT, error_key='a')
    assert len(reduced.changes) == 1
    record = build_technical_incident_commit(
        commit=_metadata(at=AT, commit_id='C1', previous='C0'),
        snapshot_after=old_snapshot,
        previous_snapshot=old_snapshot,
        open_incidents=reduced.open_incidents,
        changes=reduced.changes,
    )
    assert record is not None
    _persist(store, record)
    after = store.read_snapshot(GROUP)
    assert after.as_document()['alarms'] == old_snapshot.as_document()['alarms']
    assert snapshot_technical_incidents(after) == reduced.open_incidents


def test_v2_snapshot_rejects_invalid_incident_and_corrupt_group(tmp_path: Path):
    _, record = _commit(None, (), at=AT, error_key='a', commit_id='C1')
    assert record is not None
    document = deepcopy(record.snapshot_after.as_document())
    document['technical_incidents'][IDENTITY.canonical_key]['fingerprint'] = 'sha256:invalid'
    with pytest.raises(AlarmPersistenceValidationError, match='technical incident'):
        GroupRuntimeSnapshot(document)
    document = deepcopy(record.snapshot_after.as_document())
    document['technical_incidents'][IDENTITY.canonical_key]['priority_group'] = 'wrong'
    with pytest.raises(AlarmPersistenceCorruptionError, match='technical incident'):
        GroupRuntimeSnapshot.from_document(document)


def test_v2_commit_rejects_incorrect_schema_or_transition(tmp_path: Path):
    _, record = _commit(None, (), at=AT, error_key='a', commit_id='C1')
    assert record is not None
    document = deepcopy(record.as_document())
    document['record_schema_version'] = 'engine-commit-record.v1'
    with pytest.raises(AlarmPersistenceCorruptionError):
        EngineCommitRecord.from_document(document)
    bad = deepcopy(record.as_document())
    bad['records']['technical_incident_changes'][0]['kind'] = 'UNKNOWN'
    with pytest.raises(AlarmPersistenceCorruptionError):
        EngineCommitRecord.from_document(bad)


def test_open_incidents_reader_requires_recovered_head(tmp_path: Path, monkeypatch):
    store = AlarmPersistence(application_root=tmp_path)
    _, record = _commit(None, (), at=AT, error_key='a', commit_id='C1')
    assert record is not None
    monkeypatch.setattr(
        store, '_materialize_entry', lambda _entry: (_ for _ in ()).throw(RuntimeError('crash'))
    )
    with pytest.raises(RuntimeError, match='crash'):
        _persist(store, record)
    with pytest.raises(AlarmPersistenceCorruptionError, match='recovered'):
        read_open_technical_incidents(AlarmPersistence(application_root=tmp_path))


def test_reader_rejects_valid_but_unconfirmed_snapshot_projection(tmp_path: Path):
    store = AlarmPersistence(application_root=tmp_path)
    _, record = _commit(None, (), at=AT, error_key='a', commit_id='C1')
    assert record is not None
    _persist(store, record)
    forged = store.read_snapshot(GROUP).as_document()
    forged['technical_incidents'] = {}
    store._state.replace(store.paths.group_snapshot_relative(GROUP), forged)
    with pytest.raises(AlarmPersistenceCorruptionError, match='durable WAL'):
        read_open_technical_incidents(AlarmPersistence(application_root=tmp_path))


def test_cannot_silently_clear_open_incident_without_resolved_transition(tmp_path: Path):
    store = AlarmPersistence(application_root=tmp_path)
    reduction, record = _commit(None, (), at=AT, error_key='a', commit_id='C1')
    assert record is not None
    _persist(store, record)
    with pytest.raises(AlarmPersistenceValidationError, match='does not match transitions'):
        build_technical_incident_commit(
            commit=_metadata(at=AT + timedelta(seconds=3), commit_id='C2', previous='C1'),
            snapshot_after=store.read_snapshot(GROUP),
            previous_snapshot=store.read_snapshot(GROUP),
            open_incidents=(),
            changes=(),
        )
    assert read_open_technical_incidents(store) == reduction.open_incidents


def test_unrelated_commit_preserves_open_incident_without_duplicate_transition(tmp_path: Path):
    store = AlarmPersistence(application_root=tmp_path)
    reduced, first = _commit(None, (), at=AT, error_key='a', commit_id='C1')
    assert first is not None
    _persist(store, first)
    old = store.read_snapshot(GROUP)
    record = build_technical_incident_commit(
        commit=_metadata(at=AT + timedelta(seconds=3), commit_id='C2', previous='C1'),
        snapshot_after=old,
        previous_snapshot=old,
        open_incidents=reduced.open_incidents,
        changes=(),
        records={'journey_events': [{'event_id': 'unrelated-physical-event'}]},
    )
    assert record is not None
    assert 'technical_incident_changes' not in record.records
    _persist(store, record)
    assert read_open_technical_incidents(store) == reduced.open_incidents
    assert len(store.read_durable_records()) == 2
