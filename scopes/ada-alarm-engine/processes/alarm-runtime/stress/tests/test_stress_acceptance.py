from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from stress.acceptance import adjudicate_stress_report, assess_stress_run, require_stress_success

HEAD = {
    'segment_id': '2026-10-09T23Z#0001',
    'byte_offset': 0,
    'commit_id': 'latest',
}
ARTIFACT = {'source_key': 'alarm-configuration', 'result_id': 'test-fixture'}
RECOVERY = {
    'status': 'verified',
    'effective_head_valid': True,
    'head_aligned': True,
    'snapshots_preserved': True,
    'continuation_committed': True,
    'continuation_recovered': True,
    'error': None,
}


def _hashed(document: dict, key: str) -> dict:
    result = dict(document)
    result[key] = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()
    return result


def _write(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, sort_keys=True) + '\n', encoding='utf-8')


def _scenario(root: Path) -> Path:
    state = root / 'alarms/runtime/state'
    output = root / 'alarms/output'
    groups = [
        {'priority_group': 'priority', 'alarms': {}, 'episode': None, 'last_commit_id': 'latest'}
    ]
    _write(state / 'groups/priority.json', groups[0])
    _write(state / 'effective-head.json', {'target_artifact_ref': ARTIFACT})
    wal = root / 'alarms/runtime/journal/open/year=2026/month=10/day=09/hour=23/part-0001.jsonl'
    _write(wal, {'commit': {'commit_id': 'latest'}})
    head = {**HEAD, 'byte_offset': wal.stat().st_size}
    _write(state / 'journal-head.json', {'durable': head, 'materialized': head})
    _write(
        state / 'recovery-checkpoint-0.json',
        _hashed({'sequence': 2, 'journal_head': {'durable': head}, 'groups': groups}, 'sha256'),
    )
    first = _hashed(
        {
            'artifact_ref': ARTIFACT,
            'commit': {'commit_id': 'early'},
            'journal_position': {
                'segment_id': '2026-10-09T23Z#0000',
                'byte_offset': 200,
                'commit_id': 'early',
            },
            'previous_sha256': None,
        },
        'sha256',
    )
    last = _hashed(
        {
            'commit': {'commit_id': 'latest'},
            'journal_position': head,
            'previous_sha256': first['sha256'],
        },
        'sha256',
    )
    facts = output / 'facts/year=2026/month=10/day=09/hour=23/part-0000.jsonl'
    facts.parent.mkdir(parents=True, exist_ok=True)
    row_a = (json.dumps(first, sort_keys=True) + '\n').encode()
    row_b = (json.dumps(last, sort_keys=True) + '\n').encode()
    facts.write_bytes(row_a + row_b)
    _write(
        output / 'state/facts-export-cursor.json',
        _hashed(
            {
                'artifact_ref': ARTIFACT,
                'journal_position': head,
                'record_start': len(row_a),
                'record_end': len(row_a + row_b),
                'record_sha256': last['sha256'],
                'segment_path': facts.relative_to(output).as_posix(),
            },
            'cursor_sha256',
        ),
    )
    _write(
        output / 'current/durable-latest.json',
        _hashed(
            {
                'artifact_ref': ARTIFACT,
                'journal_position': head,
                'state': {'groups': groups},
            },
            'sha256',
        ),
    )
    return root


def _assess(
    root: Path, *, outcome: str = 'success', planned: int = 3, recovery: dict | None = None
):
    return assess_stress_run(
        application_root=root,
        runtime_result=outcome,
        planned_alarm_count=planned,
        recovery_checks=RECOVERY if recovery is None else recovery,
    )


def test_complete_integrity_and_adjudication(tmp_path: Path) -> None:
    root = _scenario(tmp_path)
    assessment = _assess(root)
    assert assessment['status'] == 'verified'
    assert all(item['status'] == 'verified' for item in assessment['checks'].values())
    report = {'result': 'success'}
    adjudicate_stress_report(report, assessment)
    assert report['result'] == 'success'
    require_stress_success(report)


@pytest.mark.parametrize(
    ('outcome', 'planned', 'recovery', 'failed_check'),
    [
        ('failed', 3, RECOVERY, 'runtime'),
        ('success', 2, RECOVERY, 'scenario'),
        ('success', 3, {**RECOVERY, 'continuation_recovered': False}, 'recovery'),
    ],
)
def test_failed_preconditions_invalidate_result(
    tmp_path: Path,
    outcome: str,
    planned: int,
    recovery: dict,
    failed_check: str,
) -> None:
    root = _scenario(tmp_path)
    assessment = _assess(root, outcome=outcome, planned=planned, recovery=recovery)
    assert assessment['status'] == 'failed'
    assert failed_check in assessment['failed_checks']
    report = {'result': outcome}
    adjudicate_stress_report(report, assessment)
    assert report['result'] == 'failed'
    assert report['runtime_result'] == outcome
    with pytest.raises(RuntimeError, match='Stress acceptance verification failed'):
        require_stress_success(report)


def test_missing_checkpoint_rejected(tmp_path: Path) -> None:
    root = _scenario(tmp_path)
    (root / 'alarms/runtime/state/recovery-checkpoint-0.json').unlink()
    assert 'rotation_compaction' in _assess(root)['failed_checks']


def test_inconsistent_retained_wal_rejected(tmp_path: Path) -> None:
    root = _scenario(tmp_path)
    wal = next((root / 'alarms/runtime/journal').rglob('*.jsonl'))
    wal.write_bytes(wal.read_bytes() + b'{}\n')
    assert 'rotation_compaction' in _assess(root)['failed_checks']


def test_facts_checksum_rejected(tmp_path: Path) -> None:
    root = _scenario(tmp_path)
    facts = next((root / 'alarms/output/facts').rglob('*.jsonl'))
    rows = facts.read_text().splitlines()
    record = json.loads(rows[1])
    record['commit']['commit_id'] = 'tampered'
    rows[1] = json.dumps(record)
    facts.write_text('\n'.join(rows) + '\n')
    assert 'facts_publication' in _assess(root)['failed_checks']


def test_facts_chain_rejected_even_with_valid_checksum(tmp_path: Path) -> None:
    root = _scenario(tmp_path)
    facts = next((root / 'alarms/output/facts').rglob('*.jsonl'))
    rows = facts.read_text().splitlines()
    record = json.loads(rows[1])
    record['previous_sha256'] = 'broken'
    rows[1] = json.dumps(_hashed({k: v for k, v in record.items() if k != 'sha256'}, 'sha256'))
    facts.write_text('\n'.join(rows) + '\n')
    assert 'facts_publication' in _assess(root)['failed_checks']


def test_corrupted_cursor_rejected(tmp_path: Path) -> None:
    root = _scenario(tmp_path)
    cursor = root / 'alarms/output/state/facts-export-cursor.json'
    value = json.loads(cursor.read_text())
    value['record_end'] += 1
    _write(cursor, value)
    assert 'facts_publication' in _assess(root)['failed_checks']


def test_current_group_mismatch_rejected_even_with_valid_checksum(tmp_path: Path) -> None:
    root = _scenario(tmp_path)
    current = root / 'alarms/output/current/durable-latest.json'
    document = json.loads(current.read_text())
    document['state']['groups'][0]['alarms'] = {'unexpected': {}}
    _write(current, _hashed({k: v for k, v in document.items() if k != 'sha256'}, 'sha256'))
    assert 'current' in _assess(root)['failed_checks']


def test_missing_current_rejected(tmp_path: Path) -> None:
    root = _scenario(tmp_path)
    (root / 'alarms/output/current/durable-latest.json').unlink()
    assert 'current' in _assess(root)['failed_checks']
