from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from importlib.resources import files

import pytest

from ada.alarms.persistence.operational import (
    GROUP_RUNTIME_SNAPSHOT_SCHEMA_VERSION,
    AlarmArtifactRefSnapshot,
    AlarmPersistence,
    AlarmPersistenceCorruptionError,
    ConfigurationAdoptionRecord,
    ConfigurationAdoptionRecordV2,
    EngineCommitMetadata,
    EngineCommitRecord,
    GroupCommitReference,
    GroupRuntimeSnapshot,
)
from ada.processes.alarm_runtime.publication import (
    AlarmCommittedFactsExporter,
    EngineFactsPublicationError,
)
from atlanticus.state import AtomicJsonStore


class _Context:
    def assert_lease_current(self):
        return None

    def fenced_mutation(self):
        return nullcontext()


def _artifact(value):
    return AlarmArtifactRefSnapshot(
        source_key='alarm-configuration',
        result_id='alarm-materialization-' + value * 64,
        manifest_sha256=value * 64,
        alarm_configuration_revision='R42',
        confirmed_tool_catalog_revision='T18',
    )


def _record(
    commit_id,
    *,
    previous_commit_id=None,
    priority_group='crusher_pressure',
    alarm_key='crusher_pressure_risk',
    evaluated_at='2026-08-23T20:00:00Z',
):
    now = datetime(2026, 8, 23, 20, tzinfo=UTC)
    snapshot = GroupRuntimeSnapshot(
        {
            'snapshot_schema_version': GROUP_RUNTIME_SNAPSHOT_SCHEMA_VERSION,
            'priority_group': priority_group,
            'last_commit_id': commit_id,
            'state_basis': {'alarm_configuration_revision': 'R42', 'tool_registry_revision': 'T18'},
            'episode': {'episode_id': f'E-{priority_group}', 'started_at': evaluated_at},
            'alarms': {
                alarm_key: {
                    'last_commit_id': commit_id,
                    'occurrence': {
                        'occurrence_id': f'O-{priority_group}',
                        'started_at': evaluated_at,
                        'configuration_revision_at_start': 'R42',
                        'tool_registry_revision_at_start': 'T18',
                        'last_evaluation': {'status': 'ACTIVE', 'evaluated_at': evaluated_at},
                        'management_cycle': 1,
                        'assignments': {'io': {'assigned_at': evaluated_at}},
                        'pending_assignments': {
                            'strategic': {
                                'due_at': (now + timedelta(minutes=30))
                                .isoformat()
                                .replace('+00:00', 'Z')
                            }
                        },
                        'next_evidence_due_at': (now + timedelta(minutes=5))
                        .isoformat()
                        .replace('+00:00', 'Z'),
                    },
                }
            },
        }
    )
    return EngineCommitRecord.create(
        commit=EngineCommitMetadata(
            commit_id=commit_id,
            cycle_id='20260823T200000000000Z',
            priority_group=priority_group,
            previous_commit_id=previous_commit_id,
            evaluated_at=evaluated_at,
            committed_at=evaluated_at,
            alarm_configuration_revision='R42',
            tool_registry_revision='T18',
            runtime_artifact_version='ada-alarms-runtime/1.0.0',
            affected_alarms=(alarm_key,),
        ),
        snapshot_after=snapshot,
        records={
            'journey_events': [
                {
                    'journey_event_id': f'J-{commit_id}',
                    'alarm_key': alarm_key,
                    'occurred_at': evaluated_at,
                }
            ]
        },
    )


def _adopt(store, target, previous=None):
    store.commit_adoption(
        ConfigurationAdoptionRecord.create(
            adoption_id='adoption-' + target,
            previous_artifact_ref=None if previous is None else _artifact(previous),
            target_artifact_ref=_artifact(target),
            effective_at='2026-08-23T20:00:00Z',
            committed_at='2026-08-23T20:00:00Z',
        ),
        assert_authority=lambda: None,
        fenced_mutation=nullcontext,
    )


def _commit(store, record):
    store.commit_batch((record,), assert_authority=lambda: None, fenced_mutation=nullcontext)


def _exporter(tmp_path, **kwargs):
    return AlarmCommittedFactsExporter(root=tmp_path, source_key='alarm-configuration', **kwargs)


def _rows(root):
    return [
        json.loads(line)
        for p in sorted((root / 'facts').rglob('*.jsonl'))
        for line in p.read_text(encoding='utf-8').splitlines()
    ]


def _cursor(root):
    return AtomicJsonStore(root_path=root).read('state/facts-export-cursor.json')


def test_exports_existing_history_from_genesis_and_is_idempotent(tmp_path):
    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    _adopt(persistence, 'a')
    record = _record('C1')
    _commit(persistence, record)
    root = tmp_path / 'output'
    exporter = _exporter(root)
    assert exporter.initialize_if_needed(context=_Context(), persistence=persistence)
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 1
    rows = _rows(root)
    assert len(rows) == 1
    assert rows[0]['schema_version'] == 4
    assert rows[0]['artifact_ref'] == _artifact('a').as_document()
    assert (
        rows[0]['journal_position']
        == persistence.read_durable_provenance()[-1].entry.end.as_document()
    )
    assert rows[0]['commit_record_hash'] == record.record_hash
    assert rows[0]['records'] == record.records
    assert rows[0]['previous_sha256'] is None
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 0
    assert exporter.initialize_if_needed(context=_Context(), persistence=persistence) is False
    assert len(list((root / 'facts').rglob('*.jsonl'))) == 1


def test_artifact_identity_changes_are_recorded_without_repeating_metadata(tmp_path):
    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    _adopt(persistence, 'a')
    first = _record('C1')
    _commit(persistence, first)
    _adopt(persistence, 'b', previous='a')
    second = _record('C2', previous_commit_id='C1')
    _commit(persistence, second)
    root = tmp_path / 'output'
    exporter = _exporter(root)
    exporter.initialize_if_needed(context=_Context(), persistence=persistence)
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 2
    rows = _rows(root)
    assert rows[0]['artifact_ref'] == _artifact('a').as_document()
    assert rows[1]['artifact_ref'] == _artifact('b').as_document()
    assert rows[1]['previous_sha256'] == rows[0]['sha256']


def test_v2_group_commits_use_confirmed_target_artifact(tmp_path):
    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    first = _record('A1', priority_group='a', alarm_key='alarm_a')
    second = _record('B1', priority_group='b', alarm_key='alarm_b')
    adoption = ConfigurationAdoptionRecordV2.create(
        adoption_id='adoption-v2-a',
        previous_artifact_ref=None,
        target_artifact_ref=_artifact('a'),
        effective_at='2026-08-23T20:00:00Z',
        committed_at='2026-08-23T20:00:00Z',
        group_commits=tuple(
            GroupCommitReference(
                priority_group=x.commit.priority_group,
                commit_id=x.commit.commit_id,
                record_hash=x.record_hash,
            )
            for x in (first, second)
        ),
    )
    persistence.commit_adoption(
        adoption,
        group_records=(first, second),
        assert_authority=lambda: None,
        fenced_mutation=nullcontext,
    )
    root = tmp_path / 'output'
    exporter = _exporter(root)
    exporter.initialize_if_needed(context=_Context(), persistence=persistence)
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 2
    rows = _rows(root)
    assert rows[0]['artifact_ref'] == _artifact('a').as_document()
    assert 'artifact_ref' not in rows[1]
    assert rows[1]['previous_sha256'] == rows[0]['sha256']
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 0


def test_cursor_failure_truncates_unconfirmed_tail_and_retries(tmp_path, monkeypatch):
    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    _adopt(persistence, 'a')
    _commit(persistence, _record('C1'))
    root = tmp_path / 'output'
    exporter = _exporter(root)
    exporter.initialize_if_needed(context=_Context(), persistence=persistence)
    original = AtomicJsonStore.replace
    failed = False

    def fail_once(self, name, document):
        nonlocal failed
        if name == 'state/facts-export-cursor.json' and not failed:
            failed = True
            raise OSError('controlled interruption')
        return original(self, name, document)

    monkeypatch.setattr(AtomicJsonStore, 'replace', fail_once)
    with pytest.raises(OSError, match='controlled interruption'):
        exporter.publish_unexported(context=_Context(), persistence=persistence)
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 1
    assert len(_rows(root)) == 1
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 0


def test_detects_tampered_last_record(tmp_path):
    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    _adopt(persistence, 'a')
    _commit(persistence, _record('C1'))
    root = tmp_path / 'output'
    exporter = _exporter(root)
    exporter.initialize_if_needed(context=_Context(), persistence=persistence)
    exporter.publish_unexported(context=_Context(), persistence=persistence)
    segment = next((root / 'facts').rglob('*.jsonl'))
    raw = segment.read_bytes()
    segment.write_bytes(raw.replace(b'J-C1', b'J-XXX'))
    with pytest.raises(EngineFactsPublicationError, match='invalid'):
        exporter.publish_unexported(context=_Context(), persistence=persistence)


def test_rotation_keeps_chain_and_bounded_file_count(tmp_path):
    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    _adopt(persistence, 'a')
    for i in range(12):
        _commit(persistence, _record(f'C{i}', previous_commit_id=f'C{i - 1}' if i else None))
    root = tmp_path / 'output'
    exporter = _exporter(root, max_segment_bytes=512)
    exporter.initialize_if_needed(context=_Context(), persistence=persistence)
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 12
    rows = _rows(root)
    assert len(rows) == 12
    assert all(b['previous_sha256'] == a['sha256'] for a, b in zip(rows, rows[1:], strict=False))
    assert len(list((root / 'facts').rglob('*.jsonl'))) == 12


def test_orphan_and_old_cursor_require_explicit_migration(tmp_path):
    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    exporter = _exporter(tmp_path / 'output')
    store = AtomicJsonStore(root_path=tmp_path / 'output')
    store.replace('facts/facts-' + 'a' * 64 + '.json', {'orphan': True})
    with pytest.raises(EngineFactsPublicationError, match='controlled v4 migration'):
        exporter.initialize_if_needed(context=_Context(), persistence=persistence)
    store.replace('state/facts-export-cursor.json', {'schema_version': 3})
    with pytest.raises(EngineFactsPublicationError, match='v4'):
        exporter.initialize_if_needed(context=_Context(), persistence=persistence)


def test_unattributed_wal_blocks_baseline(tmp_path):
    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    _commit(persistence, _record('C1'))
    with pytest.raises(AlarmPersistenceCorruptionError, match='origin'):
        _exporter(tmp_path / 'output').initialize_if_needed(
            context=_Context(), persistence=persistence
        )


def test_v4_schema_declares_committed_collections():
    schema = json.loads(
        files('ada.contracts.alarms')
        .joinpath('schemas/engine_committed_facts_stream.v4.schema.json')
        .read_text(encoding='utf-8')
    )
    assert schema['properties']['schema_version']['const'] == 4
    assert 'configuration_rebases' in schema['properties']['records']['properties']
    assert 'technical_incident_changes' in schema['properties']['records']['properties']


def test_rotation_multiple_records_per_segment_and_restart(tmp_path):
    from ada.contracts.alarms.facts_stream import iter_committed_facts

    application_root = tmp_path / 'runtime'
    persistence = AlarmPersistence(application_root=application_root)
    _adopt(persistence, 'a')
    for i in range(20):
        _commit(
            persistence,
            _record(
                f'C{i}',
                previous_commit_id=f'C{i - 1}' if i else None,
            ),
        )
    root = tmp_path / 'output'
    exporter = _exporter(root, max_segment_bytes=4000)
    exporter.initialize_if_needed(context=_Context(), persistence=persistence)
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 20
    segments = sorted((root / 'facts').rglob('*.jsonl'))
    assert 1 < len(segments) < 20
    assert any(len(path.read_bytes().splitlines()) > 1 for path in segments)
    rows = list(iter_committed_facts(root=root))
    assert [row.commit['commit_id'] for row in rows] == [f'C{i}' for i in range(20)]
    assert all(row.position.artifact_ref == _artifact('a').as_document() for row in rows)
    assert len(list(iter_committed_facts(root=root, after=rows[9].position))) == 10

    recovered = AlarmPersistence(application_root=application_root)
    recovered.recover(assert_authority=lambda: None, fenced_mutation=nullcontext)
    restarted = _exporter(root, max_segment_bytes=4000)
    assert not restarted.initialize_if_needed(context=_Context(), persistence=recovered)
    assert restarted.publish_unexported(context=_Context(), persistence=recovered) == 0
    _commit(recovered, _record('C20', previous_commit_id='C19'))
    assert restarted.publish_unexported(context=_Context(), persistence=recovered) == 1
    rows = list(iter_committed_facts(root=root))
    assert len(rows) == 21
    assert rows[-1].commit['commit_id'] == 'C20'
    assert len(list(iter_committed_facts(root=root, after=rows[19].position))) == 1


def test_cursor_interruption_during_segment_rollover_recovers_without_duplicate(
    tmp_path, monkeypatch
):
    from ada.contracts.alarms.facts_stream import iter_committed_facts

    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    _adopt(persistence, 'a')
    first, second = _record('C1'), _record('C2', previous_commit_id='C1')
    _commit(persistence, first)
    root = tmp_path / 'output'
    exporter = _exporter(root, max_segment_bytes=512)
    exporter.initialize_if_needed(context=_Context(), persistence=persistence)
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 1
    _commit(persistence, second)

    original = AtomicJsonStore.replace
    interrupted = False

    def interrupt_cursor(self, name, document):
        nonlocal interrupted
        if name == 'state/facts-export-cursor.json' and not interrupted:
            interrupted = True
            raise OSError('interrupted after rotated append')
        return original(self, name, document)

    monkeypatch.setattr(AtomicJsonStore, 'replace', interrupt_cursor)
    with pytest.raises(OSError, match='interrupted after rotated append'):
        exporter.publish_unexported(context=_Context(), persistence=persistence)
    assert len(list(iter_committed_facts(root=root))) == 1
    restarted = _exporter(root, max_segment_bytes=512)
    assert not restarted.initialize_if_needed(context=_Context(), persistence=persistence)
    assert restarted.publish_unexported(context=_Context(), persistence=persistence) == 1
    assert restarted.publish_unexported(context=_Context(), persistence=persistence) == 0
    rows = list(iter_committed_facts(root=root))
    assert [row.commit['commit_id'] for row in rows] == ['C1', 'C2']
    assert len(list((root / 'facts').rglob('*.jsonl'))) == 2
