from __future__ import annotations

import hashlib
import json

import pytest

from ada.contracts.alarms.facts_stream import (
    FactsStreamReadError,
    iter_committed_facts,
)

FIRST = 'facts/year=2026/month=10/day=09/hour=16/part-0000.jsonl'
SECOND = 'facts/year=2026/month=10/day=09/hour=16/part-0001.jsonl'
ARTIFACT = {
    'source_key': 'alarm-configuration',
    'result_id': 'alarm-materialization-' + 'a' * 64,
    'manifest_sha256': 'a' * 64,
    'resolution_key': {
        'alarm_configuration_revision': 'R1',
        'confirmed_tool_catalog_revision': 'T1',
    },
}


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()


def _bytes(row):
    return (
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode() + b'\n'
    )


def _record(i, previous, *, anchored):
    row = {
        'schema_version': 4,
        'journal_position': {
            'segment_id': '2026-10-09T16Z#0000',
            'byte_offset': (i + 1) * 100,
            'commit_id': f'C{i}',
        },
        'commit': {
            'commit_id': f'C{i}',
            'cycle_id': f'cycle-{i}',
            'priority_group': 'group',
            'previous_commit_id': f'C{i - 1}' if i else None,
            'evaluated_at': '2026-10-09T16:00:00Z',
            'committed_at': '2026-10-09T16:00:00Z',
            'alarm_configuration_revision': 'R1',
            'tool_registry_revision': 'T1',
            'runtime_artifact_version': 'runtime/1',
            'affected_alarms': ['alarm'],
        },
        'commit_record_hash': 'sha256:' + f'{i:064x}',
        'previous_sha256': previous,
        'records': {'journey_events': [{'journey_event_id': f'J{i}'}]},
    }
    if anchored:
        row['document_type'] = 'ada_command_center_engine_committed_facts_stream'
        row['artifact_ref'] = ARTIFACT
    row['sha256'] = _digest(row)
    return row


def _fixture(root):
    first = _record(0, None, anchored=True)
    second = _record(1, first['sha256'], anchored=False)
    third = _record(2, second['sha256'], anchored=True)
    one = root / FIRST
    one.parent.mkdir(parents=True, exist_ok=True)
    one.write_bytes(_bytes(first) + _bytes(second))
    two = root / SECOND
    two.write_bytes(_bytes(third))
    cursor = {
        'document_type': 'ada_command_center_engine_facts_export_cursor',
        'schema_version': 4,
        'artifact_ref': ARTIFACT,
        'journal_position': third['journal_position'],
        'segment_path': SECOND,
        'record_start': 0,
        'record_end': len(_bytes(third)),
        'record_sha256': third['sha256'],
    }
    cursor['cursor_sha256'] = _digest(cursor)
    path = root / 'state/facts-export-cursor.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cursor), encoding='utf-8')
    return one, two, path


def test_reader_resumes_from_confirmed_position_without_replaying_history(tmp_path):
    _fixture(tmp_path)
    items = list(iter_committed_facts(root=tmp_path))
    assert [x.commit['commit_id'] for x in items] == ['C0', 'C1', 'C2']
    assert all(x.position.artifact_ref == ARTIFACT for x in items)
    assert [
        x.commit['commit_id']
        for x in iter_committed_facts(
            root=tmp_path,
            after=items[0].position,
        )
    ] == ['C1', 'C2']
    assert [
        x.commit['commit_id']
        for x in iter_committed_facts(
            root=tmp_path,
            after=items[1].position,
        )
    ] == ['C2']
    assert list(iter_committed_facts(root=tmp_path, after=items[2].position)) == []


def test_reader_ignores_unconfirmed_tail_in_last_segment(tmp_path):
    _, segment, _ = _fixture(tmp_path)
    with segment.open('ab') as handle:
        handle.write(b'{"orphan":true}\n')
    assert len(list(iter_committed_facts(root=tmp_path))) == 3


def test_reader_rejects_corruption_in_previous_segment(tmp_path):
    first, _, _ = _fixture(tmp_path)
    first.write_bytes(first.read_bytes().replace(b'J0', b'XX'))
    with pytest.raises(FactsStreamReadError, match='invalid|integrity'):
        list(iter_committed_facts(root=tmp_path))


def test_reader_rejects_missing_segment(tmp_path):
    first, _, _ = _fixture(tmp_path)
    first.unlink()
    with pytest.raises(FactsStreamReadError, match='initial|sequence|chain'):
        list(iter_committed_facts(root=tmp_path))


def test_reader_rejects_invalid_cursor_digest(tmp_path):
    _, _, path = _fixture(tmp_path)
    cursor = json.loads(path.read_text())
    cursor['record_end'] += 1
    path.write_text(json.dumps(cursor))
    with pytest.raises(FactsStreamReadError, match='integrity'):
        list(iter_committed_facts(root=tmp_path))


def test_reader_rejects_invalid_resume_position(tmp_path):
    _, _, _ = _fixture(tmp_path)
    items = list(iter_committed_facts(root=tmp_path))
    from dataclasses import replace

    invalid = replace(items[0].position, record_sha256='0' * 64)
    with pytest.raises(FactsStreamReadError, match='digest'):
        list(iter_committed_facts(root=tmp_path, after=invalid))


def test_reader_rejects_truncated_committed_segment(tmp_path):
    _, segment, _ = _fixture(tmp_path)
    segment.write_bytes(segment.read_bytes()[:-2])
    with pytest.raises(FactsStreamReadError, match='invalid|reachable'):
        list(iter_committed_facts(root=tmp_path))


def test_reader_rejects_missing_middle_part(tmp_path):
    _, _, _ = _fixture(tmp_path)
    source = tmp_path / SECOND
    target = source.with_name('part-0002.jsonl')
    source.rename(target)
    cursor_path = tmp_path / 'state/facts-export-cursor.json'
    cursor = json.loads(cursor_path.read_text())
    cursor['segment_path'] = target.relative_to(tmp_path).as_posix()
    cursor['cursor_sha256'] = _digest({k: v for k, v in cursor.items() if k != 'cursor_sha256'})
    cursor_path.write_text(json.dumps(cursor))
    with pytest.raises(FactsStreamReadError, match='incomplete'):
        list(iter_committed_facts(root=tmp_path))
