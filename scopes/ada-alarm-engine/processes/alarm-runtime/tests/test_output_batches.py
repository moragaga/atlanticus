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


def _artifact(value: str) -> AlarmArtifactRefSnapshot:
    return AlarmArtifactRefSnapshot(
        source_key='alarm-configuration',
        result_id='alarm-materialization-' + value * 64,
        manifest_sha256=value * 64,
        alarm_configuration_revision='R42',
        confirmed_tool_catalog_revision='T18',
    )


def _record(
    commit_id: str,
    *,
    previous_commit_id: str | None = None,
    priority_group: str = 'crusher_pressure',
    alarm_key: str = 'crusher_pressure_risk',
) -> EngineCommitRecord:
    now = datetime(2026, 8, 23, 20, tzinfo=UTC)
    timestamp = '2026-08-23T20:00:00Z'
    snapshot = GroupRuntimeSnapshot(
        {
            'snapshot_schema_version': GROUP_RUNTIME_SNAPSHOT_SCHEMA_VERSION,
            'priority_group': priority_group,
            'last_commit_id': commit_id,
            'state_basis': {
                'alarm_configuration_revision': 'R42',
                'tool_registry_revision': 'T18',
            },
            'episode': {'episode_id': f'E-{priority_group}', 'started_at': timestamp},
            'alarms': {
                alarm_key: {
                    'last_commit_id': commit_id,
                    'occurrence': {
                        'occurrence_id': f'O-{priority_group}',
                        'started_at': timestamp,
                        'configuration_revision_at_start': 'R42',
                        'tool_registry_revision_at_start': 'T18',
                        'last_evaluation': {'status': 'ACTIVE', 'evaluated_at': timestamp},
                        'management_cycle': 1,
                        'assignments': {'io': {'assigned_at': timestamp}},
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
            evaluated_at=timestamp,
            committed_at=timestamp,
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
                    'occurred_at': timestamp,
                }
            ]
        },
    )


def _adopt(store: AlarmPersistence, target: str, previous: str | None = None) -> None:
    store.commit_adoption(
        ConfigurationAdoptionRecord.create(
            adoption_id=f'adoption-{target}',
            previous_artifact_ref=None if previous is None else _artifact(previous),
            target_artifact_ref=_artifact(target),
            effective_at='2026-08-23T20:00:00Z',
            committed_at='2026-08-23T20:00:00Z',
        ),
        assert_authority=lambda: None,
        fenced_mutation=nullcontext,
    )


def _commit(store: AlarmPersistence, record: EngineCommitRecord) -> None:
    store.commit_batch((record,), assert_authority=lambda: None, fenced_mutation=nullcontext)


def _exporter(tmp_path) -> AlarmCommittedFactsExporter:
    return AlarmCommittedFactsExporter(root=tmp_path, source_key='alarm-configuration')


def _batch(store: AtomicJsonStore, record: EngineCommitRecord) -> dict:
    name = f'facts/facts-{record.record_hash.removeprefix("sha256:")}.json'
    return store.read(name)


def test_exports_existing_history_from_genesis_and_is_idempotent(tmp_path):
    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    _adopt(persistence, 'a')
    record = _record('C1')
    _commit(persistence, record)
    exporter = _exporter(tmp_path / 'output')
    context = _Context()
    assert exporter.initialize_if_needed(context=context, persistence=persistence)
    assert exporter.publish_unexported(context=context, persistence=persistence) == 1
    store = AtomicJsonStore(root_path=tmp_path / 'output')
    batch = _batch(store, record)
    assert batch['schema_version'] == 3
    assert batch['artifact_ref'] == _artifact('a').as_document()
    assert (
        batch['journal_position']
        == persistence.read_durable_provenance()[1].entry.end.as_document()
    )
    assert batch['commit_record_hash'] == record.record_hash
    assert batch['records'] == record.records
    assert batch['previous_batch'] is None
    assert exporter.publish_unexported(context=context, persistence=persistence) == 0
    assert exporter.initialize_if_needed(context=context, persistence=persistence) is False


def test_distinguishes_two_artifacts_with_identical_revisions(tmp_path):
    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    _adopt(persistence, 'a')
    first = _record('C1')
    _commit(persistence, first)
    _adopt(persistence, 'b', previous='a')
    second = _record('C2', previous_commit_id='C1')
    _commit(persistence, second)
    exporter = _exporter(tmp_path / 'output')
    exporter.initialize_if_needed(context=_Context(), persistence=persistence)
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 2
    store = AtomicJsonStore(root_path=tmp_path / 'output')
    first_batch, second_batch = _batch(store, first), _batch(store, second)
    assert first_batch['artifact_ref'] == _artifact('a').as_document()
    assert second_batch['artifact_ref'] == _artifact('b').as_document()
    assert second_batch['previous_batch'] == {
        'batch_id': first_batch['batch_id'],
        'sha256': first_batch['sha256'],
    }


def test_v2_group_commits_use_target_artifact_before_adoption(tmp_path):
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
                priority_group=item.commit.priority_group,
                commit_id=item.commit.commit_id,
                record_hash=item.record_hash,
            )
            for item in (first, second)
        ),
    )
    persistence.commit_adoption(
        adoption,
        group_records=(first, second),
        assert_authority=lambda: None,
        fenced_mutation=nullcontext,
    )
    exporter = _exporter(tmp_path / 'output')
    exporter.initialize_if_needed(context=_Context(), persistence=persistence)
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 2
    store = AtomicJsonStore(root_path=tmp_path / 'output')
    assert _batch(store, first)['artifact_ref'] == _artifact('a').as_document()
    assert _batch(store, second)['artifact_ref'] == _artifact('a').as_document()
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 0


def test_cursor_failure_retries_without_corrupting_chain(tmp_path, monkeypatch):
    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    _adopt(persistence, 'a')
    record = _record('C1')
    _commit(persistence, record)
    exporter = _exporter(tmp_path / 'output')
    exporter.initialize_if_needed(context=_Context(), persistence=persistence)
    original = AtomicJsonStore.replace
    failed = False

    def failing_once(self, name, document):
        nonlocal failed
        if name == 'state/facts-export-cursor.json' and not failed:
            failed = True
            raise RuntimeError('controlled interruption')
        return original(self, name, document)

    monkeypatch.setattr(AtomicJsonStore, 'replace', failing_once)
    with pytest.raises(RuntimeError, match='controlled interruption'):
        exporter.publish_unexported(context=_Context(), persistence=persistence)
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 1
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 0


def test_rejects_tampered_last_batch(tmp_path):
    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    _adopt(persistence, 'a')
    record = _record('C1')
    _commit(persistence, record)
    exporter = _exporter(tmp_path / 'output')
    exporter.initialize_if_needed(context=_Context(), persistence=persistence)
    exporter.publish_unexported(context=_Context(), persistence=persistence)
    store = AtomicJsonStore(root_path=tmp_path / 'output')
    path = f'facts/facts-{record.record_hash.removeprefix("sha256:")}.json'
    batch = store.read(path)
    batch['records']['journey_events'][0]['journey_event_id'] = 'altered'
    store.replace(path, batch)
    with pytest.raises(EngineFactsPublicationError, match='invalid'):
        exporter.publish_unexported(context=_Context(), persistence=persistence)


def test_orphan_and_legacy_checkpoint_require_controlled_migration(tmp_path):
    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    exporter = _exporter(tmp_path / 'output')
    store = AtomicJsonStore(root_path=tmp_path / 'output')
    store.replace('facts/facts-' + 'a' * 64 + '.json', {'orphan': True})
    with pytest.raises(EngineFactsPublicationError, match='controlled migration'):
        exporter.initialize_if_needed(context=_Context(), persistence=persistence)
    store.replace('state/facts-export-cursor.json', {'schema_version': 2})
    with pytest.raises(EngineFactsPublicationError, match='v3'):
        exporter.initialize_if_needed(context=_Context(), persistence=persistence)


def test_provenance_errors_block_baseline(tmp_path):
    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    _commit(persistence, _record('C1'))
    exporter = _exporter(tmp_path / 'output')
    with pytest.raises(AlarmPersistenceCorruptionError, match='origin'):
        exporter.initialize_if_needed(context=_Context(), persistence=persistence)


def test_v3_schema_includes_all_current_record_collections():
    path = files('ada.contracts.alarms').joinpath(
        'schemas/engine_committed_facts_batch.v3.schema.json'
    )
    schema = json.loads(path.read_text(encoding='utf-8'))
    assert schema['properties']['schema_version']['const'] == 3
    assert 'configuration_rebases' in schema['properties']['records']['properties']
    assert 'technical_incident_changes' in schema['properties']['records']['properties']
    assert 'minItems' not in schema['properties']['commit']['properties']['affected_alarms']
