from __future__ import annotations

import json
from contextlib import nullcontext
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from ada.alarms.persistence.operational import (
    AlarmArtifactRefSnapshot,
    JournalPosition,
)
from ada.contracts.alarms.facts_stream import iter_committed_facts
from ada.processes.alarm_runtime.publication import output_batches as batches
from atlanticus.state import AtomicJsonStore


class _Context:
    def assert_lease_current(self):
        return None

    def fenced_mutation(self):
        return nullcontext()


@dataclass(frozen=True)
class _Commit:
    commit_id: str
    alarm_configuration_revision: str = 'R1'
    tool_registry_revision: str = 'T1'

    def as_document(self):
        return {
            'commit_id': self.commit_id,
            'cycle_id': self.commit_id,
            'priority_group': 'group',
            'previous_commit_id': None,
            'evaluated_at': '2026-10-10T10:00:00Z',
            'committed_at': '2026-10-10T10:00:00Z',
            'alarm_configuration_revision': self.alarm_configuration_revision,
            'tool_registry_revision': self.tool_registry_revision,
            'runtime_artifact_version': 'runtime/1',
            'affected_alarms': ['a'],
        }


class _Record:
    def __init__(self, number, revision='R1'):
        self.commit = _Commit(f'C{number}', alarm_configuration_revision=revision)
        self.record_hash = 'sha256:' + f'{number:064x}'
        self.records = {
            'journey_events': [{'event_id': f'J{number}', 'event_key': 'occurrence_started'}]
        }


class _Persistence:
    def __init__(self, items):
        self.items = items
        self.after_values = []

    def read_durable_provenance(self, *, after=None):
        self.after_values.append(after)
        if after is None:
            return tuple(self.items)
        for i, item in enumerate(self.items):
            if item.entry.end == after:
                return tuple(self.items[i + 1 :])
        raise ValueError('Unknown journal cursor')


def _artifact(revision='R1'):
    return AlarmArtifactRefSnapshot(
        source_key='alarm-configuration',
        result_id='alarm-materialization-' + 'a' * 64,
        manifest_sha256='a' * 64,
        alarm_configuration_revision=revision,
        confirmed_tool_catalog_revision='T1',
    )


def _items(n, *, hour=10, revisions=None):
    revisions = revisions or {}
    return [
        SimpleNamespace(
            artifact_ref=_artifact(revisions.get(i, 'R1')),
            entry=SimpleNamespace(
                end=JournalPosition(
                    segment_id=f'2026-10-10T{hour:02d}Z#0000',
                    byte_offset=100 * (i + 1),
                    commit_id=f'C{i}',
                ),
                record=_Record(i, revisions.get(i, 'R1')),
            ),
        )
        for i in range(n)
    ]


@pytest.fixture(autouse=True)
def _fake_source_types(monkeypatch):
    monkeypatch.setattr(batches, 'EngineCommitRecord', _Record)
    monkeypatch.setattr(batches, 'AlarmPersistence', _Persistence)


def _start(root, items, **limits):
    persistence = _Persistence(items)
    exporter = batches.AlarmCommittedFactsExporter(
        root=root, source_key='alarm-configuration', **limits
    )
    exporter.initialize_if_needed(context=_Context(), persistence=persistence)
    return exporter, persistence


def _rows(root):
    return [
        json.loads(line)
        for path in sorted((root / 'facts').rglob('*.jsonl'))
        for line in path.read_text().splitlines()
    ]


def test_many_commits_share_one_append_and_one_cursor(tmp_path, monkeypatch):
    exporter, persistence = _start(tmp_path, _items(25))
    appends = []
    original = batches._append

    def measure(path, payload):
        appends.append(len(payload))
        return original(path, payload)

    monkeypatch.setattr(batches, '_append', measure)
    store = AtomicJsonStore(root_path=tmp_path)
    before = store.read('state/facts-export-cursor.json')
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 25
    after = store.read('state/facts-export-cursor.json')
    assert before != after
    assert len(appends) == 1
    assert sum(appends) == sum(path.stat().st_size for path in (tmp_path / 'facts').rglob('*.jsonl'))
    assert [item.commit['commit_id'] for item in iter_committed_facts(root=tmp_path)] == [
        f'C{i}' for i in range(25)
    ]


def test_no_new_commits_performs_no_append(tmp_path, monkeypatch):
    exporter, persistence = _start(tmp_path, _items(2))
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 2
    monkeypatch.setattr(batches, '_append', lambda *_: pytest.fail('Unexpected append'))
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 0
    assert len(_rows(tmp_path)) == 2


def test_record_limit_forces_bounded_batches_without_duplication(tmp_path, monkeypatch):
    exporter, persistence = _start(tmp_path, _items(8), max_batch_records=3)
    calls = []
    original = batches._append

    def measure(path, payload):
        calls.append(payload)
        return original(path, payload)

    monkeypatch.setattr(batches, '_append', measure)
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 8
    assert len(calls) == 3
    assert [row['commit']['commit_id'] for row in _rows(tmp_path)] == [f'C{i}' for i in range(8)]


def test_byte_limit_forces_bounded_batches(tmp_path, monkeypatch):
    exporter, persistence = _start(tmp_path, _items(5), max_batch_bytes=550)
    calls = []
    original = batches._append

    def measure(path, payload):
        calls.append(payload)
        return original(path, payload)

    monkeypatch.setattr(batches, '_append', measure)
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 5
    assert len(calls) >= 2
    assert len(list(iter_committed_facts(root=tmp_path))) == 5


def test_rotation_and_hash_chain_remain_readable(tmp_path):
    exporter, persistence = _start(tmp_path, _items(6), max_segment_bytes=900)
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 6
    files = sorted((tmp_path / 'facts').rglob('*.jsonl'))
    assert len(files) >= 3
    records = list(iter_committed_facts(root=tmp_path))
    assert len(records) == 6
    rows = _rows(tmp_path)
    assert all(
        after['previous_sha256'] == before['sha256']
        for before, after in zip(rows, rows[1:], strict=False)
    )


def test_cross_hour_never_appends_to_previous_hour(tmp_path):
    items = _items(3, hour=10) + _items(2, hour=11)
    items[-2].entry.end = JournalPosition('2026-10-10T11Z#0000', 400, 'C3')
    items[-2].entry.record = _Record(3)
    items[-1].entry.end = JournalPosition('2026-10-10T11Z#0000', 500, 'C4')
    items[-1].entry.record = _Record(4)
    exporter, persistence = _start(tmp_path, items)
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 5
    assert len(list((tmp_path / 'facts').rglob('*.jsonl'))) == 2
    assert len(list(iter_committed_facts(root=tmp_path))) == 5


def test_failure_before_cursor_commit_replays_without_duplicates(tmp_path, monkeypatch):
    exporter, persistence = _start(tmp_path, _items(8))
    original = AtomicJsonStore.replace
    failed = False

    def fail_once(self, name, document):
        nonlocal failed
        if name == 'state/facts-export-cursor.json' and not failed:
            failed = True
            raise OSError('forced failure')
        return original(self, name, document)

    monkeypatch.setattr(AtomicJsonStore, 'replace', fail_once)
    with pytest.raises(OSError, match='forced failure'):
        exporter.publish_unexported(context=_Context(), persistence=persistence)
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 8
    assert [item.commit['commit_id'] for item in iter_committed_facts(root=tmp_path)] == [
        f'C{i}' for i in range(8)
    ]


def test_failure_after_first_confirmed_batch_resumes_at_exact_boundary(tmp_path, monkeypatch):
    exporter, persistence = _start(tmp_path, _items(7), max_batch_records=3)
    original = AtomicJsonStore.replace
    checkpoints = 0

    def fail_second(self, name, document):
        nonlocal checkpoints
        if name == 'state/facts-export-cursor.json':
            checkpoints += 1
            if checkpoints == 2:
                raise OSError('second batch interrupted')
        return original(self, name, document)

    monkeypatch.setattr(AtomicJsonStore, 'replace', fail_second)
    with pytest.raises(OSError, match='second batch interrupted'):
        exporter.publish_unexported(context=_Context(), persistence=persistence)
    assert len(_rows(tmp_path)) >= 3
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 4
    assert len(list(iter_committed_facts(root=tmp_path))) == 7


def test_configuration_artifact_change_keeps_stream_anchor(tmp_path):
    exporter, persistence = _start(tmp_path, _items(4, revisions={2: 'R2', 3: 'R2'}))
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 4
    rows = _rows(tmp_path)
    assert 'artifact_ref' in rows[0]
    assert 'artifact_ref' not in rows[1]
    assert 'artifact_ref' in rows[2]
    assert 'artifact_ref' not in rows[3]
    assert len(list(iter_committed_facts(root=tmp_path))) == 4


def test_stream_resumes_after_a_position_inside_confirmed_batch(tmp_path):
    exporter, persistence = _start(tmp_path, _items(10))
    assert exporter.publish_unexported(context=_Context(), persistence=persistence) == 10
    entries = list(iter_committed_facts(root=tmp_path))
    resumed = list(iter_committed_facts(root=tmp_path, after=entries[3].position))
    assert [item.commit['commit_id'] for item in resumed] == [f'C{i}' for i in range(4, 10)]
