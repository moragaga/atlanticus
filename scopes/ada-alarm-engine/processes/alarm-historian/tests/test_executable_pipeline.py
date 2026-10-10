from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager

from ada.alarms.history import history_destination
from ada.contracts.alarms.history_projection import AlarmHistoryDomain
from ada.processes.alarm_historian.bootstrap import load_configuration
from ada.processes.alarm_historian.checkpoint import AlarmHistorianCheckpointStore
from ada.processes.alarm_historian.composition import build_composition
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.datasets.runtime import DatasetRuntime


class _Context:
    def __init__(self):
        self.facts = {}
        self.depth = 0
        self.work = 0

    def assert_lease_current(self):
        assert self.depth == 0

    def raise_if_cancelled(self):
        return None

    @contextmanager
    def fenced_mutation(self):
        assert self.depth == 0
        self.depth += 1
        try:
            yield
        finally:
            self.depth -= 1

    def mark_iteration_work(self):
        self.work += 1

    def set_iteration_fact(self, name, value):
        self.facts[name] = value


def _digest(document):
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    ).hexdigest()


def _write_facts(producer_root):
    output = producer_root / 'alarms' / 'output'
    path = output / 'facts/year=2026/month=10/day=10/hour=12/part-0000.jsonl'
    path.parent.mkdir(parents=True)
    journal = {'commit_id': 'C-1', 'segment_id': 'J-1', 'byte_offset': 10}
    artifact = {
        'source_key': 'alarms',
        'resolution_key': {
            'alarm_configuration_revision': 'r1',
            'confirmed_tool_catalog_revision': 't1',
        },
    }
    document = {
        'document_type': 'ada_command_center_engine_committed_facts_stream',
        'schema_version': 4,
        'journal_position': journal,
        'commit': {
            'commit_id': 'C-1',
            'priority_group': 'plant',
            'alarm_configuration_revision': 'r1',
            'tool_registry_revision': 't1',
        },
        'commit_record_hash': 'sha256:' + 'f' * 64,
        'previous_sha256': None,
        'artifact_ref': artifact,
        'records': {
            'occurrence_changes': [{
                'alarm_key': 'plant/high_pressure',
                'occurrence_id': 'occ-1',
                'kind': 'STARTED',
                'started_at': '2026-10-10T12:00:00Z',
            }],
        },
    }
    digest = _digest(document)
    raw = json.dumps({**document, 'sha256': digest}, sort_keys=True, ensure_ascii=False,
                     separators=(',', ':')).encode() + b'\n'
    path.write_bytes(raw)
    cursor = {
        'document_type': 'ada_command_center_engine_facts_export_cursor',
        'schema_version': 4,
        'artifact_ref': artifact,
        'journal_position': journal,
        'segment_path': path.relative_to(output).as_posix(),
        'record_start': 0,
        'record_end': len(raw),
        'record_sha256': digest,
    }
    cursor_path = output / 'state' / 'facts-export-cursor.json'
    cursor_path.parent.mkdir(parents=True)
    cursor_path.write_text(json.dumps({**cursor, 'cursor_sha256': _digest(cursor)}))


def test_end_to_end_facts_parquet_checkpoint_and_relaunch(tmp_path):
    producer = tmp_path / 'runtime-source'
    _write_facts(producer)
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'historian-target',
        'VOLUMEN_PATH': str(tmp_path),
        'ALARM_HISTORIAN_PRODUCER_APPLICATION': 'runtime-source',
        'ALARM_HISTORIAN_STREAM_ID': 'plant-stream-stable',
        'ALARM_HISTORIAN_MAX_RECORDS': '1',
    }
    resolved = load_configuration(process_root=tmp_path, environ=values)
    first = build_composition(configuration=resolved)
    result = first.job.run_iteration(_Context())
    assert result.records_read == 1
    assert result.facts_projected == 1
    assert result.targets_committed == 1
    assert result.checkpoint_advanced
    checkpoint_store = AlarmHistorianCheckpointStore(
        root=tmp_path / 'historian-target' / 'alarms' / 'historian',
        stream_id='plant-stream-stable',
        producer_application='runtime-source',
    )
    checkpoint = checkpoint_store.read()
    assert checkpoint.stream_id == 'plant-stream-stable'
    assert checkpoint.producer_application == 'runtime-source'

    from ada.contracts.alarms.facts_stream import iter_committed_facts
    from ada.contracts.alarms.history_projection import project_committed_alarm_facts

    committed = next(iter_committed_facts(root=producer / 'alarms' / 'output'))
    fact = project_committed_alarm_facts(facts=committed, stream_id='plant-stream-stable').facts[0]
    assert fact.domain == AlarmHistoryDomain.LIFECYCLE
    definition, target = history_destination(fact)
    dataset = DatasetRuntime(
        store=ParquetDatasetStore(root=tmp_path / 'historian-target' / 'alarms')
    )
    rows = dataset.read_table(definition=definition, target=target).table.to_pylist()
    assert len(rows) == 1
    assert rows[0]['historian_fact_id'] == fact.historian_fact_id

    second = build_composition(configuration=resolved)
    again = second.job.run_iteration(_Context())
    assert again.records_read == 0
    assert not again.checkpoint_advanced
    assert checkpoint_store.read().position == checkpoint.position
    rows_again = dataset.read_table(definition=definition, target=target).table.to_pylist()
    assert rows_again == rows
