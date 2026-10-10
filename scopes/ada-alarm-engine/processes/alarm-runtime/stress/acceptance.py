from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _document(path: Path) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'Expected a JSON object: {path}')
    return data


def _authenticated(document: dict, key: str) -> bool:
    expected = document.get(key)
    if not isinstance(expected, str) or len(expected) != 64:
        return False
    unsigned = {name: value for name, value in document.items() if name != key}
    payload = json.dumps(unsigned, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(payload).hexdigest() == expected


def _position(value: dict) -> tuple[str, int]:
    if not isinstance(value, dict):
        raise ValueError('Missing journal position')
    segment_id = value.get('segment_id')
    offset = value.get('byte_offset')
    commit_id = value.get('commit_id')
    if (
        not isinstance(segment_id, str)
        or not segment_id
        or not isinstance(offset, int)
        or offset < 1
    ):
        raise ValueError('Invalid journal position')
    if not isinstance(commit_id, str) or not commit_id:
        raise ValueError('Invalid journal commit ID')
    return segment_id, offset


def _assert_head(application_root: Path) -> tuple[dict, dict]:
    state = application_root / 'alarms/runtime/state'
    head = _document(state / 'journal-head.json')
    if head.get('durable') != head.get('materialized'):
        raise ValueError('Journal durable and materialized heads differ')
    _position(head['durable'])
    effective = _document(state / 'effective-head.json')
    if not effective.get('target_artifact_ref'):
        raise ValueError('Effective artifact reference is missing')
    return head['durable'], effective


def _assert_rotation(application_root: Path, head: dict) -> dict:
    root = application_root / 'alarms/runtime'
    checkpoints = [
        _document(p) for p in sorted((root / 'state').glob('recovery-checkpoint-*.json'))
    ]
    checkpoints = [p for p in checkpoints if _authenticated(p, 'sha256')]
    if not checkpoints or max(p.get('sequence', -1) for p in checkpoints) < 2:
        raise ValueError('Durable checkpoint progression not demonstrated')
    last = max(checkpoints, key=lambda item: item['sequence'])
    if _position(last['journal_head']['durable']) > _position(head):
        raise ValueError('Checkpoint is ahead of durable HEAD')
    journal = root / 'journal'
    files = sorted(path for path in journal.rglob('*.jsonl') if path.is_file())
    if not files:
        raise ValueError('No retained WAL records')
    segments = set()
    last_commit_id = None
    last_offset = 0
    for path in files:
        offset = 0
        for line in path.read_bytes().splitlines(keepends=True):
            if not line.strip():
                continue
            if not line.endswith(b'\n'):
                raise ValueError('Incomplete retained WAL record')
            row = json.loads(line)
            last_commit_id = row['commit']['commit_id']
            offset += len(line)
        if not offset:
            raise ValueError('Empty retained WAL segment')
        day = next(part[5:] for part in path.parts if part.startswith('year='))
        month = next(part[6:] for part in path.parts if part.startswith('month='))
        date = next(part[4:] for part in path.parts if part.startswith('day='))
        hour = next(part[5:] for part in path.parts if part.startswith('hour='))
        part = int(path.stem.removeprefix('part-'))
        segment_id = f'{day}-{month}-{date}T{hour}Z#{part:04d}'
        segments.add(segment_id)
        last_offset = offset
    latest_segment = max(segments)
    if (
        latest_segment != head['segment_id']
        or last_commit_id != head['commit_id']
        or last_offset != head['byte_offset']
    ):
        raise ValueError('Retained WAL tip differs from durable HEAD')
    if (
        not latest_segment.rsplit('#', 1)[-1].isdigit()
        or int(latest_segment.rsplit('#', 1)[-1]) < 1
    ):
        raise ValueError('No WAL segment rotation demonstrated')
    return {
        'checkpoint_sequence': last['sequence'],
        'retained_segments': len(segments),
        'retained_first_segment': min(segments),
    }


def _assert_facts(
    application_root: Path, head: dict, effective: dict, retained_first_segment: str
) -> dict:
    output = application_root / 'alarms/output'
    paths = sorted((output / 'facts').rglob('*.jsonl'))
    if not paths:
        raise ValueError('No published facts')
    last_document = None
    previous_hash = None
    previous_position = None
    commit_ids = set()
    first_position = None
    last_segment_path = None
    last_start = 0
    last_end = 0
    count = 0
    for path in paths:
        offset = 0
        raw = path.read_bytes()
        for line in raw.splitlines(keepends=True):
            if not line.strip() or not line.endswith(b'\n'):
                raise ValueError('Malformed or truncated facts record')
            start = offset
            offset += len(line)
            document = json.loads(line)
            if not isinstance(document, dict) or not _authenticated(document, 'sha256'):
                raise ValueError('Facts record checksum mismatch')
            if document.get('previous_sha256') != previous_hash:
                raise ValueError('Facts hash chain is discontinuous')
            commit = document.get('commit', {}).get('commit_id')
            if not commit or commit in commit_ids:
                raise ValueError('Missing or duplicated facts commit ID')
            commit_ids.add(commit)
            position = document.get('journal_position')
            key = _position(position)
            if position['commit_id'] != commit or (
                previous_position is not None and key <= previous_position
            ):
                raise ValueError('Facts journal positions are not strictly increasing')
            if (
                document.get('artifact_ref') is not None
                and document['artifact_ref'] != effective['target_artifact_ref']
            ):
                raise ValueError('Facts artifact reference differs from effective configuration')
            if count == 0 and document.get('artifact_ref') != effective['target_artifact_ref']:
                raise ValueError('Facts stream header is missing or mismatched')
            first_position = first_position or key
            previous_position = key
            previous_hash = document['sha256']
            last_document = document
            last_segment_path = path.relative_to(output).as_posix()
            last_start = start
            last_end = offset
            count += 1
    if first_position[0] >= retained_first_segment:
        raise ValueError('Published facts do not demonstrate retired historical WAL')
    if last_document['journal_position'] != head:
        raise ValueError('Published facts are not aligned with HEAD')
    cursor = _document(output / 'state/facts-export-cursor.json')
    if not _authenticated(cursor, 'cursor_sha256'):
        raise ValueError('Facts cursor checksum mismatch')
    expected = {
        'segment_path': last_segment_path,
        'record_start': last_start,
        'record_end': last_end,
        'record_sha256': last_document['sha256'],
        'journal_position': head,
        'artifact_ref': effective['target_artifact_ref'],
    }
    if any(cursor.get(key) != value for key, value in expected.items()):
        raise ValueError('Facts cursor is not aligned with final published record')
    return {'batches': count, 'last_position': head}


def _assert_current(application_root: Path, head: dict, effective: dict) -> dict:
    output = application_root / 'alarms/output'
    current = _document(output / 'current/durable-latest.json')
    if not _authenticated(current, 'sha256'):
        raise ValueError('CURRENT checksum mismatch')
    if current.get('journal_position') != head:
        raise ValueError('CURRENT journal position differs from HEAD')
    if current.get('artifact_ref') != effective['target_artifact_ref']:
        raise ValueError('CURRENT artifact reference differs from effective configuration')
    actual = current.get('state', {}).get('groups')
    if not isinstance(actual, list) or not actual:
        raise ValueError('CURRENT has no group snapshots')
    expected = {
        p.stem: _document(p)
        for p in (application_root / 'alarms/runtime/state/groups').glob('*.json')
    }
    observed = {group.get('priority_group'): group for group in actual if isinstance(group, dict)}
    if len(observed) != len(actual) or expected != observed:
        raise ValueError('CURRENT groups do not match durable snapshots')
    return {'groups': len(observed)}


def assess_stress_run(
    *, application_root: Path, runtime_result: str, planned_alarm_count: int, recovery_checks: dict
) -> dict:
    recovery_checks = recovery_checks if isinstance(recovery_checks, dict) else {}
    checks = {}
    failures = []

    def check(name: str, operation):
        try:
            details = operation()
            checks[name] = {'status': 'verified', **(details or {})}
        except (KeyError, TypeError, ValueError, OSError, StopIteration) as error:
            checks[name] = {'status': 'failed', 'error': str(error)}
            failures.append(name)

    check(
        'runtime',
        lambda: (
            {}
            if str(runtime_result).lower().split('.')[-1] == 'success'
            else _reject('Runtime did not finish successfully')
        ),
    )
    check(
        'scenario',
        lambda: (
            {} if planned_alarm_count == 3 else _reject('Expected exactly three planned alarms')
        ),
    )
    check(
        'recovery',
        lambda: (
            {}
            if (
                recovery_checks.get('status') == 'verified'
                and recovery_checks.get('effective_head_valid') is True
                and recovery_checks.get('head_aligned') is True
                and recovery_checks.get('snapshots_preserved') is True
                and recovery_checks.get('continuation_committed') is True
                and recovery_checks.get('continuation_recovered') is True
                and recovery_checks.get('error') is None
            )
            else _reject('Recovery or durable continuation did not verify')
        ),
    )

    head = None
    effective = None
    rotation = None

    def check_head():
        nonlocal head, effective
        head, effective = _assert_head(application_root)
        return {}

    def check_rotation():
        nonlocal rotation
        if head is None:
            raise ValueError('HEAD verification is required')
        rotation = _assert_rotation(application_root, head)
        return rotation

    def check_facts():
        if head is None or rotation is None or effective is None:
            raise ValueError('HEAD and rotation verification are required')
        return _assert_facts(application_root, head, effective, rotation['retained_first_segment'])

    def check_current():
        if head is None or effective is None:
            raise ValueError('HEAD verification is required')
        return _assert_current(application_root, head, effective)

    check('head', check_head)
    check('rotation_compaction', check_rotation)
    check('facts_publication', check_facts)
    check('current', check_current)
    return {
        'status': 'verified' if not failures else 'failed',
        'failed_checks': failures,
        'checks': checks,
    }


def _reject(message: str):
    raise ValueError(message)


def adjudicate_stress_report(report: dict, assessment: dict) -> None:
    report['acceptance_checks'] = assessment
    if assessment['status'] != 'verified':
        report['runtime_result'] = report['result']
        report['result'] = 'failed'


def require_stress_success(report: dict) -> None:
    if report['acceptance_checks']['status'] != 'verified':
        failed = ', '.join(report['acceptance_checks']['failed_checks'])
        raise RuntimeError(f'Stress acceptance verification failed: {failed}')
