from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from ada_command_center.alarms.persistence import (
    AlarmArtifactRefSnapshot,
    AlarmPersistence,
    JournalPosition,
)
from ada_command_center.processes.alarms_runtime.publication.output_batches import (
    AlarmCommittedFactsExporter,
    EngineFactsPublicationError,
)
from atlanticus.state import AtomicJsonStore


def _pin(revision='R1'):
    return AlarmArtifactRefSnapshot(
        source_key='alarms',
        result_id='alarm-materialization-' + '0' * 64,
        manifest_sha256='1' * 64,
        alarm_configuration_revision=revision,
        confirmed_tool_catalog_revision='C1',
    )


def _entry(offset, revision='R1', records=None):
    if records is None:
        records = {
            'journey_events': [
                {
                    'event_id': f'event-{offset}',
                    'event_key': 'occurrence_started',
                    'alarm_key': 'mina/a',
                }
            ],
            'evidence_records': [],
        }
    commit_id = f'commit-{offset}'
    commit = SimpleNamespace(
        commit_id=commit_id,
        alarm_configuration_revision=revision,
        tool_registry_revision='C1',
        as_document=lambda: {'commit_id': commit_id, 'alarm_configuration_revision': revision},
    )
    record = SimpleNamespace(commit=commit, record_hash=f'sha256:{offset:064x}', records=records)
    return SimpleNamespace(
        record=record,
        end=JournalPosition(
            segment_id='2026-09-28T14Z#0001', byte_offset=offset, commit_id=commit_id
        ),
    )


class _Persistence(AlarmPersistence):
    def __init__(self, entries, baseline=None):
        self.entries = entries
        self.baseline = baseline

    def read_head(self):
        return SimpleNamespace(aligned=True, durable=self.baseline)

    def read_durable_records(self, *, after=None):
        return tuple(
            item
            for item in self.entries
            if after is None or item.end.byte_offset > after.byte_offset
        )


class _Context:
    def __init__(self):
        self.fences = 0

    def assert_lease_current(self):
        return None

    @contextmanager
    def fenced_mutation(self):
        self.fences += 1
        yield


def test_exports_only_durable_facts_and_replay_is_idempotent(tmp_path):
    entry = _entry(10)
    exporter = AlarmCommittedFactsExporter(root=tmp_path, source_key='alarms')
    context = _Context()
    persistence = _Persistence([])
    assert exporter.initialize_if_needed(context=context, persistence=persistence, pin=_pin())
    persistence.entries.append(entry)
    assert exporter.publish_unexported(context=context, persistence=persistence, pin=_pin()) == 1
    store = AtomicJsonStore(root_path=tmp_path, max_document_bytes=None)
    batch = store.read(f'facts/facts-{entry.record.record_hash.removeprefix("sha256:")}.json')
    assert batch['artifact_ref']['resolution_key']['alarm_configuration_revision'] == 'R1'
    assert batch['commit_record_hash'] == entry.record.record_hash
    assert batch['journal_position'] == entry.end.as_document()
    assert batch['records'] == {'journey_events': entry.record.records['journey_events']}
    assert exporter.publish_unexported(context=context, persistence=persistence, pin=_pin()) == 0
    assert context.fences == 2


def test_pending_commit_must_match_selected_effective_revision(tmp_path):
    exporter = AlarmCommittedFactsExporter(root=tmp_path, source_key='alarms')
    context = _Context()
    persistence = _Persistence([])
    exporter.initialize_if_needed(context=context, persistence=persistence, pin=_pin())
    persistence.entries.append(_entry(10, revision='R0'))
    with pytest.raises(EngineFactsPublicationError, match='EFFECTIVE revision'):
        exporter.publish_unexported(context=context, persistence=persistence, pin=_pin())
    assert context.fences == 1


def test_after_confirmed_export_new_revision_is_accepted(tmp_path):
    exporter = AlarmCommittedFactsExporter(root=tmp_path, source_key='alarms')
    context = _Context()
    persistence = _Persistence([])
    exporter.initialize_if_needed(context=context, persistence=persistence, pin=_pin())
    persistence.entries.append(_entry(10))
    assert exporter.publish_unexported(context=context, persistence=persistence, pin=_pin()) == 1
    persistence.entries.append(_entry(20, revision='R2'))
    assert (
        exporter.publish_unexported(context=context, persistence=persistence, pin=_pin('R2')) == 1
    )


def test_retries_after_file_is_written_but_cursor_write_fails(tmp_path, monkeypatch):
    exporter = AlarmCommittedFactsExporter(root=tmp_path, source_key='alarms')
    persistence = _Persistence([])
    exporter.initialize_if_needed(context=_Context(), persistence=persistence, pin=_pin())
    persistence.entries.append(_entry(10))
    original = AtomicJsonStore.replace
    interrupted = False

    def replace(store, path, value):
        nonlocal interrupted
        if str(path).endswith('facts-export-cursor.json') and not interrupted:
            interrupted = True
            raise RuntimeError('controlled interruption')
        return original(store, path, value)

    monkeypatch.setattr(AtomicJsonStore, 'replace', replace)
    with pytest.raises(RuntimeError, match='controlled interruption'):
        exporter.publish_unexported(context=_Context(), persistence=persistence, pin=_pin())
    assert exporter.publish_unexported(context=_Context(), persistence=persistence, pin=_pin()) == 1


def test_existing_batch_cannot_be_silently_overwritten(tmp_path):
    entry = _entry(10)
    exporter = AlarmCommittedFactsExporter(root=tmp_path, source_key='alarms')
    path = f'facts/facts-{entry.record.record_hash.removeprefix("sha256:")}.json'
    persistence = _Persistence([])
    exporter.initialize_if_needed(context=_Context(), persistence=persistence, pin=_pin())
    persistence.entries.append(entry)
    AtomicJsonStore(root_path=tmp_path).replace(path, {'corrupt': True})
    with pytest.raises(EngineFactsPublicationError, match='differs from durable WAL'):
        exporter.publish_unexported(context=_Context(), persistence=persistence, pin=_pin())


def test_tampered_last_published_batch_rejects_checkpoint(tmp_path):
    entry = _entry(10)
    exporter = AlarmCommittedFactsExporter(root=tmp_path, source_key='alarms')
    persistence = _Persistence([])
    exporter.initialize_if_needed(context=_Context(), persistence=persistence, pin=_pin())
    persistence.entries.append(entry)
    exporter.publish_unexported(context=_Context(), persistence=persistence, pin=_pin())
    store = AtomicJsonStore(root_path=tmp_path)
    path = f'facts/facts-{entry.record.record_hash.removeprefix("sha256:")}.json'
    document = store.read(path)
    document['records']['journey_events'][0]['event_key'] = 'altered'
    store.replace(path, document)
    with pytest.raises(EngineFactsPublicationError, match='invalid'):
        exporter.publish_unexported(context=_Context(), persistence=persistence, pin=_pin())


def test_baseline_excludes_older_wal_and_keeps_new_facts(tmp_path):
    older = _entry(10, revision='R0')
    recent = _entry(20, revision='R1')
    exporter = AlarmCommittedFactsExporter(root=tmp_path, source_key='alarms')
    persistence = _Persistence([], baseline=older.end)
    assert exporter.initialize_if_needed(context=_Context(), persistence=persistence, pin=_pin())
    persistence.entries.append(recent)
    assert exporter.publish_unexported(context=_Context(), persistence=persistence, pin=_pin()) == 1
    store = AtomicJsonStore(root_path=tmp_path)
    assert (
        store.read(f'facts/facts-{older.record.record_hash.removeprefix("sha256:")}.json') is None
    )
    assert (
        store.read(f'facts/facts-{recent.record.record_hash.removeprefix("sha256:")}.json')
        is not None
    )


def test_initialization_is_idempotent(tmp_path):
    exporter = AlarmCommittedFactsExporter(root=tmp_path, source_key='alarms')
    persistence = _Persistence([])
    assert exporter.initialize_if_needed(context=_Context(), persistence=persistence, pin=_pin())
    assert not exporter.initialize_if_needed(
        context=_Context(), persistence=persistence, pin=_pin()
    )


def test_existing_history_must_not_be_silently_skipped(tmp_path):
    older = _entry(10, revision='R0')
    exporter = AlarmCommittedFactsExporter(root=tmp_path, source_key='alarms')
    persistence = _Persistence([older], baseline=older.end)
    with pytest.raises(EngineFactsPublicationError, match='initial export baseline'):
        exporter.initialize_if_needed(context=_Context(), persistence=persistence, pin=_pin())
    assert AtomicJsonStore(root_path=tmp_path).read('state/facts-export-cursor.json') is None
