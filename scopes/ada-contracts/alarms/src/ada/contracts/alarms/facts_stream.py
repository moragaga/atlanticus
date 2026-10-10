from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

_CURSOR_PATH = 'state/facts-export-cursor.json'
_CURSOR_TYPE = 'ada_command_center_engine_facts_export_cursor'
_RECORD_TYPE = 'ada_command_center_engine_committed_facts_stream'
_SEGMENT_PATTERN = re.compile(
    r'facts/year=\d{4}/month=\d{2}/day=\d{2}/hour=\d{2}/part-(\d{4})\.jsonl'
)
_RECORD_KEYS = frozenset(
    {
        'assignment_changes',
        'configuration_rebases',
        'deactivation_effects',
        'deactivation_requests',
        'episode_changes',
        'evidence_records',
        'input_receipts',
        'journey_events',
        'management_effects',
        'occurrence_changes',
        'technical_incident_changes',
    }
)


class FactsStreamReadError(ValueError):
    pass


def _encode(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode(
        'utf-8'
    )


def _digest(value: dict) -> str:
    return hashlib.sha256(_encode(value)).hexdigest()


def _require_path(value: str) -> str:
    if not isinstance(value, str) or _SEGMENT_PATTERN.fullmatch(value) is None:
        raise FactsStreamReadError('Invalid facts segment path')
    return value


def _load_cursor(root: Path) -> dict:
    path = root / _CURSOR_PATH
    try:
        cursor = json.loads(path.read_bytes())
    except (OSError, ValueError, UnicodeError, TypeError) as error:
        raise FactsStreamReadError('FACTS publication cursor is unavailable') from error
    if not isinstance(cursor, dict) or (
        set(cursor)
        != {
            'document_type',
            'schema_version',
            'artifact_ref',
            'journal_position',
            'segment_path',
            'record_start',
            'record_end',
            'record_sha256',
            'cursor_sha256',
        }
        or cursor.get('document_type') != _CURSOR_TYPE
        or cursor.get('schema_version') != 4
        or cursor.get('cursor_sha256')
        != _digest({k: v for k, v in cursor.items() if k != 'cursor_sha256'})
    ):
        raise FactsStreamReadError('FACTS publication cursor integrity is invalid')
    if cursor.get('journal_position') is None:
        if any(
            cursor.get(k) is not None
            for k in ('artifact_ref', 'segment_path', 'record_start', 'record_end', 'record_sha256')
        ):
            raise FactsStreamReadError('Initial FACTS cursor is invalid')
        return cursor
    _require_path(cursor.get('segment_path'))
    if (
        not isinstance(cursor.get('record_start'), int)
        or isinstance(cursor['record_start'], bool)
        or not isinstance(cursor.get('record_end'), int)
        or isinstance(cursor['record_end'], bool)
        or cursor['record_start'] < 0
        or cursor['record_end'] <= cursor['record_start']
        or not isinstance(cursor.get('record_sha256'), str)
        or not re.fullmatch(r'[0-9a-f]{64}', cursor['record_sha256'])
        or not isinstance(cursor.get('artifact_ref'), dict)
        or not isinstance(cursor.get('journal_position'), dict)
    ):
        raise FactsStreamReadError('FACTS committed cursor fields are invalid')
    return cursor


@dataclass(frozen=True, slots=True)
class FactsStreamPosition:
    segment_path: str
    record_start: int
    record_end: int
    record_sha256: str
    artifact_ref: dict


@dataclass(frozen=True, slots=True)
class CommittedFacts:
    position: FactsStreamPosition
    journal_position: dict
    commit: dict
    commit_record_hash: str
    records: dict


def _read_record(root: Path, position: FactsStreamPosition) -> dict:
    _require_path(position.segment_path)
    if (
        not isinstance(position.record_start, int)
        or not isinstance(position.record_end, int)
        or (
            isinstance(position.record_start, bool)
            or isinstance(position.record_end, bool)
            or position.record_start < 0
            or position.record_end <= position.record_start
        )
    ):
        raise FactsStreamReadError('FACTS resume offset is invalid')
    try:
        with (root / position.segment_path).open('rb') as handle:
            handle.seek(position.record_start)
            raw = handle.read(position.record_end - position.record_start)
        row = json.loads(raw)
        if not isinstance(row, dict) or _encode(row) + b'\n' != raw:
            raise ValueError('Invalid canonical record')
    except (OSError, ValueError, UnicodeError, TypeError) as error:
        raise FactsStreamReadError('FACTS resume record is unavailable') from error
    if row.get('sha256') != position.record_sha256 or (
        _digest({k: v for k, v in row.items() if k != 'sha256'}) != position.record_sha256
    ):
        raise FactsStreamReadError('FACTS resume record digest differs')
    return row


def iter_committed_facts(
    *, root: Path, after: FactsStreamPosition | None = None
) -> Iterator[CommittedFacts]:
    if not isinstance(root, Path) or not root.is_absolute():
        raise ValueError('FACTS root must be an absolute Path')
    head = _load_cursor(root)
    if head.get('journal_position') is None:
        if after is not None:
            raise FactsStreamReadError('FACTS resume position is ahead of empty publication')
        return
    head_path = head['segment_path']
    head_key = (head_path, head['record_end'])
    last_sha: str | None = None
    artifact: dict | None = None
    start_path: str | None = None
    start_end = 0
    if after is not None:
        if not isinstance(after, FactsStreamPosition) or not isinstance(after.artifact_ref, dict):
            raise FactsStreamReadError('FACTS resume position is invalid')
        row = _read_record(root, after)
        if row.get('artifact_ref') is not None and row['artifact_ref'] != after.artifact_ref:
            raise FactsStreamReadError('FACTS resume artifact is inconsistent')
        if (after.segment_path, after.record_end) > head_key:
            raise FactsStreamReadError('FACTS resume position is ahead of publication')
        if (after.segment_path, after.record_end) == head_key:
            if (
                after.record_sha256 != head['record_sha256']
                or after.artifact_ref != head['artifact_ref']
                or row.get('journal_position') != head['journal_position']
            ):
                raise FactsStreamReadError('FACTS resume position differs from publication')
            return
        start_path, start_end = after.segment_path, after.record_end
        last_sha, artifact = after.record_sha256, after.artifact_ref
    paths = sorted(
        p
        for p in (root / 'facts').rglob('*.jsonl')
        if _SEGMENT_PATTERN.fullmatch(p.relative_to(root).as_posix())
    )
    prior: str | None = None
    found_head = False
    last_position: FactsStreamPosition | None = None
    last_journal_position: dict | None = None
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if relative > head_path:
            break
        if start_path is not None and relative < start_path:
            continue
        if prior is not None:
            current_hour, current_part = relative.rsplit('/', 1)
            previous_hour, previous_part = prior.rsplit('/', 1)
            expected_part = int(previous_part[5:9]) + 1 if current_hour == previous_hour else 0
            if int(current_part[5:9]) != expected_part:
                raise FactsStreamReadError('FACTS segment sequence is incomplete')
        elif start_path is None and int(path.stem[5:]) != 0:
            raise FactsStreamReadError('FACTS stream has no initial segment')
        prior = relative
        offset = start_end if relative == start_path else 0
        limit = head['record_end'] if relative == head_path else path.stat().st_size
        if offset > limit:
            raise FactsStreamReadError('FACTS resume offset exceeds committed data')
        with path.open('rb') as handle:
            handle.seek(offset)
            while offset < limit:
                raw = handle.readline(limit - offset)
                try:
                    row = json.loads(raw)
                    if not isinstance(row, dict) or _encode(row) + b'\n' != raw:
                        raise ValueError('Non-canonical record')
                except (ValueError, UnicodeError, TypeError) as error:
                    raise FactsStreamReadError('FACTS committed record is invalid') from error
                expected = _digest({k: v for k, v in row.items() if k != 'sha256'})
                if (
                    row.get('sha256') != expected
                    or row.get('schema_version') != 4
                    or set(row)
                    - {
                        'schema_version',
                        'document_type',
                        'journal_position',
                        'commit',
                        'commit_record_hash',
                        'previous_sha256',
                        'records',
                        'artifact_ref',
                        'sha256',
                    }
                ):
                    raise FactsStreamReadError('FACTS record integrity is invalid')
                if row.get('previous_sha256') != last_sha:
                    raise FactsStreamReadError('FACTS record chain is broken')
                anchored = row.get('artifact_ref')
                if offset == 0 and (
                    row.get('document_type') != _RECORD_TYPE or not isinstance(anchored, dict)
                ):
                    raise FactsStreamReadError('FACTS segment has no artifact anchor')
                if anchored is not None:
                    if not isinstance(anchored, dict):
                        raise FactsStreamReadError('FACTS artifact anchor is invalid')
                    artifact = anchored
                if (
                    not isinstance(artifact, dict)
                    or not isinstance(row.get('commit'), dict)
                    or (
                        not isinstance(row.get('journal_position'), dict)
                        or row['commit'].get('commit_id')
                        != row['journal_position'].get('commit_id')
                        or row['commit'].get('alarm_configuration_revision')
                        != artifact.get('resolution_key', {}).get('alarm_configuration_revision')
                        or row['commit'].get('tool_registry_revision')
                        != artifact.get('resolution_key', {}).get('confirmed_tool_catalog_revision')
                        or not isinstance(row.get('records'), dict)
                        or set(row['records']) - _RECORD_KEYS
                        or not all(isinstance(v, list) and v for v in row['records'].values())
                        or not isinstance(row.get('commit_record_hash'), str)
                        or re.fullmatch(r'sha256:[0-9a-f]{64}', row['commit_record_hash']) is None
                    )
                ):
                    raise FactsStreamReadError('FACTS record contracts are invalid')
                end = offset + len(raw)
                position = FactsStreamPosition(relative, offset, end, expected, artifact)
                last_position = position
                last_journal_position = row['journal_position']
                last_sha = expected
                offset = end
                yield CommittedFacts(
                    position=position,
                    journal_position=row['journal_position'],
                    commit=row['commit'],
                    commit_record_hash=row['commit_record_hash'],
                    records=row['records'],
                )
        if relative == head_path:
            found_head = True
            break
    if (
        not found_head
        or last_position is None
        or (
            last_position.record_end != head['record_end']
            or last_position.record_start != head['record_start']
            or last_position.record_sha256 != head['record_sha256']
            or last_position.artifact_ref != head['artifact_ref']
            or last_journal_position != head['journal_position']
        )
    ):
        raise FactsStreamReadError('FACTS confirmed cursor is not reachable')
