from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ada.alarms.persistence.operational import (
    AlarmArtifactRefSnapshot,
    AlarmPersistence,
    AlarmPersistenceCorruptionError,
    EngineCommitRecord,
    JournalPosition,
)
from ada.alarms.persistence.operational.models import parse_segment_id
from atlanticus.state import AtomicJsonStore

DOCUMENT_TYPE = 'ada_command_center_engine_committed_facts_stream'
CURSOR_DOCUMENT_TYPE = 'ada_command_center_engine_facts_export_cursor'
SCHEMA_VERSION = 4
_CURSOR = 'state/facts-export-cursor.json'
_SEGMENT_LIMIT = 2 * 1024 * 1024
_BATCH_LIMIT = 256 * 1024
_BATCH_RECORD_LIMIT = 256
_RECORD_COLLECTIONS = frozenset(
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


class EngineFactsPublicationError(RuntimeError):
    pass


class FactsExportContext(Protocol):
    def assert_lease_current(self) -> None: ...

    def fenced_mutation(self): ...


def _encode(document: dict[str, object]) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode(
        'utf-8'
    )


def _digest(document: dict[str, object]) -> str:
    return hashlib.sha256(_encode(document)).hexdigest()


def _seal_cursor(document: dict[str, object]) -> dict[str, object]:
    sealed = dict(document)
    sealed['cursor_sha256'] = _digest(
        {key: value for key, value in sealed.items() if key != 'cursor_sha256'}
    )
    return sealed


def _new_cursor() -> dict[str, object]:
    return _seal_cursor(
        {
            'document_type': CURSOR_DOCUMENT_TYPE,
            'schema_version': SCHEMA_VERSION,
            'artifact_ref': None,
            'journal_position': None,
            'segment_path': None,
            'record_start': None,
            'record_end': None,
            'record_sha256': None,
        }
    )


def _segment_path(position: JournalPosition, part: int) -> str:
    year, month, day, hour, _ = parse_segment_id(position.segment_id)
    return (
        f'facts/year={year:04d}/month={month:02d}/day={day:02d}/'
        f'hour={hour:02d}/part-{part:04d}.jsonl'
    )


def _part(path: str) -> int:
    return int(Path(path).stem.removeprefix('part-'))


def _entry(
    record: EngineCommitRecord,
    position: JournalPosition,
    artifact: AlarmArtifactRefSnapshot,
    previous_sha256: str | None,
    include_artifact: bool,
) -> dict[str, object]:
    if (
        record.commit.alarm_configuration_revision != artifact.alarm_configuration_revision
        or record.commit.tool_registry_revision != artifact.confirmed_tool_catalog_revision
    ):
        raise EngineFactsPublicationError('Committed facts do not match their durable artifact')
    if re.fullmatch(r'sha256:[0-9a-f]{64}', record.record_hash) is None:
        raise EngineFactsPublicationError('Committed record hash is invalid')
    if set(record.records) - _RECORD_COLLECTIONS:
        raise EngineFactsPublicationError('Committed facts contain unsupported record collections')
    document: dict[str, object] = {
        'schema_version': SCHEMA_VERSION,
        'journal_position': position.as_document(),
        'commit': record.commit.as_document(),
        'commit_record_hash': record.record_hash,
        'previous_sha256': previous_sha256,
        'records': {key: value for key, value in record.records.items() if value},
    }
    if include_artifact:
        document['document_type'] = DOCUMENT_TYPE
        document['artifact_ref'] = artifact.as_document()
    document['sha256'] = _digest(document)
    return document


def _read_line(path: Path, start: int, end: int) -> dict[str, object]:
    try:
        with path.open('rb') as handle:
            handle.seek(start)
            raw = handle.read(end - start)
        if len(raw) != end - start or not raw.endswith(b'\n'):
            raise ValueError('missing committed record bytes')
        line = json.loads(raw)
        if not isinstance(line, dict) or _encode(line) + b'\n' != raw:
            raise ValueError('non-canonical committed record')
        return line
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise EngineFactsPublicationError(
            'Last committed facts record is unavailable or invalid'
        ) from error


def _verify_checkpoint(root: Path, checkpoint: dict) -> JournalPosition | None:
    if (
        not isinstance(checkpoint, dict)
        or set(checkpoint) != set(_new_cursor())
        or (
            checkpoint.get('document_type') != CURSOR_DOCUMENT_TYPE
            or checkpoint.get('schema_version') != SCHEMA_VERSION
        )
    ):
        raise EngineFactsPublicationError('Facts export checkpoint requires the v4 contract')
    if checkpoint['cursor_sha256'] != _digest(
        {key: value for key, value in checkpoint.items() if key != 'cursor_sha256'}
    ):
        raise EngineFactsPublicationError('Facts export checkpoint digest is invalid')
    if checkpoint['journal_position'] is None:
        if any(
            checkpoint[key] is not None
            for key in (
                'artifact_ref',
                'segment_path',
                'record_start',
                'record_end',
                'record_sha256',
            )
        ):
            raise EngineFactsPublicationError('Initial facts export checkpoint is invalid')
        return None
    try:
        position = JournalPosition.from_document(checkpoint['journal_position'])
        artifact = AlarmArtifactRefSnapshot.from_document(checkpoint['artifact_ref'])
        relative = checkpoint['segment_path']
        start, end = checkpoint['record_start'], checkpoint['record_end']
        expected = checkpoint['record_sha256']
        if (
            not isinstance(relative, str)
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or start < 0
            or end <= start
            or not isinstance(expected, str)
            or len(expected) != 64
        ):
            raise ValueError('checkpoint offset is invalid')
        path = _segment_path(position, _part(relative))
        if relative != path:
            raise ValueError('checkpoint segment path is invalid')
        row = _read_line(root / relative, start, end)
        if (
            row.get('schema_version') != SCHEMA_VERSION
            or row.get('sha256') != expected
            or _digest({key: value for key, value in row.items() if key != 'sha256'}) != expected
            or row.get('journal_position') != position.as_document()
            or row.get('commit', {}).get('commit_id') != position.commit_id
        ):
            raise ValueError('checkpoint does not match committed record')
        if row.get('artifact_ref') is not None and row['artifact_ref'] != artifact.as_document():
            raise ValueError('checkpoint artifact is invalid')
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        AlarmPersistenceCorruptionError,
    ) as error:
        raise EngineFactsPublicationError(
            'Last committed facts record is unavailable or invalid'
        ) from error
    return position


def _truncate_orphan(path: Path, committed_size: int) -> None:
    if not path.exists() and committed_size:
        raise EngineFactsPublicationError('Committed facts segment is missing')
    if path.exists():
        with path.open('r+b') as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() < committed_size:
                raise EngineFactsPublicationError('Facts segment is shorter than committed cursor')
            if handle.tell() != committed_size:
                handle.truncate(committed_size)
                handle.flush()
                os.fsync(handle.fileno())


def _append(path: Path, payload: bytes) -> tuple[int, int]:
    created = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('ab') as handle:
        start = handle.tell()
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    if created:
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return start, start + len(payload)


@dataclass(slots=True)
class AlarmCommittedFactsExporter:
    root: Path
    source_key: str
    max_segment_bytes: int = _SEGMENT_LIMIT
    max_batch_bytes: int = _BATCH_LIMIT
    max_batch_records: int = _BATCH_RECORD_LIMIT

    def __post_init__(self) -> None:
        if not isinstance(self.root, Path) or not self.root.is_absolute():
            raise ValueError('Engine output root must be an absolute Path')
        if not isinstance(self.source_key, str) or not self.source_key.strip():
            raise ValueError('Engine output source_key must be non-empty text')
        if not isinstance(self.max_segment_bytes, int) or self.max_segment_bytes < 512:
            raise ValueError('max_segment_bytes must be at least 512')
        if (
            not isinstance(self.max_batch_bytes, int)
            or isinstance(self.max_batch_bytes, bool)
            or self.max_batch_bytes <= 0
            or not isinstance(self.max_batch_records, int)
            or isinstance(self.max_batch_records, bool)
            or self.max_batch_records <= 0
        ):
            raise ValueError('FACTS batch limits must be positive integers')

    def exported_position(self) -> JournalPosition | None:
        checkpoint = AtomicJsonStore(root_path=self.root, max_document_bytes=None).read(_CURSOR)
        if checkpoint is None:
            raise EngineFactsPublicationError('Facts export cursor is missing')
        return _verify_checkpoint(self.root, checkpoint)

    def initialize_if_needed(
        self, *, context: FactsExportContext, persistence: AlarmPersistence
    ) -> bool:
        if not isinstance(persistence, AlarmPersistence):
            raise TypeError('persistence must be AlarmPersistence')
        store = AtomicJsonStore(root_path=self.root, max_document_bytes=None)
        checkpoint = store.read(_CURSOR)
        if checkpoint is not None:
            _verify_checkpoint(self.root, checkpoint)
            return False
        facts_root = self.root / 'facts'
        if facts_root.exists() and any(facts_root.iterdir()):
            raise EngineFactsPublicationError('Existing facts require controlled v4 migration')
        context.assert_lease_current()
        persistence.read_durable_provenance()
        with context.fenced_mutation():
            checkpoint = store.read(_CURSOR)
            if checkpoint is not None:
                _verify_checkpoint(self.root, checkpoint)
                return False
            if facts_root.exists() and any(facts_root.iterdir()):
                raise EngineFactsPublicationError('Existing facts require controlled v4 migration')
            store.replace(_CURSOR, _new_cursor())
        return True

    def publish_unexported(
        self, *, context: FactsExportContext, persistence: AlarmPersistence
    ) -> int:
        if not isinstance(persistence, AlarmPersistence):
            raise TypeError('persistence must be AlarmPersistence')
        store = AtomicJsonStore(root_path=self.root, max_document_bytes=None)
        checkpoint = store.read(_CURSOR)
        if checkpoint is None:
            raise EngineFactsPublicationError('Facts export baseline must be initialized first')
        cursor = _verify_checkpoint(self.root, checkpoint)
        context.assert_lease_current()
        entries = persistence.read_durable_provenance(after=cursor)
        pending: list[bytes] = []
        pending_bytes = 0
        working = checkpoint
        count = 0

        def flush() -> None:
            nonlocal checkpoint, pending_bytes
            if not pending:
                return
            relative = working['segment_path']
            previous_end = (
                checkpoint['record_end']
                if checkpoint['segment_path'] == relative
                else 0
            )
            path = self.root / relative
            with context.fenced_mutation():
                if store.read(_CURSOR) != checkpoint:
                    raise EngineFactsPublicationError(
                        'Facts export checkpoint changed during publication'
                    )
                if checkpoint['segment_path'] and checkpoint['segment_path'] != relative:
                    _truncate_orphan(
                        self.root / checkpoint['segment_path'], checkpoint['record_end']
                    )
                _truncate_orphan(path, previous_end)
                start, end = _append(path, b''.join(pending))
                if start != previous_end or end != working['record_end']:
                    raise EngineFactsPublicationError(
                        'Facts append position differs from checkpoint'
                    )
                updated = _seal_cursor(working)
                store.replace(_CURSOR, updated)
            checkpoint = updated
            pending.clear()
            pending_bytes = 0

        for item in entries:
            if item.artifact_ref.source_key != self.source_key:
                raise EngineFactsPublicationError(
                    'Durable artifact source_key does not match output'
                )
            record = item.entry.record
            if not isinstance(record, EngineCommitRecord):
                continue
            context.assert_lease_current()
            position = item.entry.end
            current_path = working['segment_path']
            candidate_path = _segment_path(position, 0)
            same_hour = isinstance(current_path, str) and (
                str(Path(current_path).parent) == str(Path(candidate_path).parent)
            )
            relative = current_path if same_hour else candidate_path
            artifact_changed = working['artifact_ref'] != item.artifact_ref.as_document()
            payload_doc = _entry(
                record,
                position,
                item.artifact_ref,
                working['record_sha256'],
                include_artifact=artifact_changed or not same_hour,
            )
            payload = _encode(payload_doc) + b'\n'
            previous_end = working['record_end'] if same_hour else 0
            if same_hour and previous_end + len(payload) > self.max_segment_bytes:
                relative = _segment_path(position, _part(current_path) + 1)
                payload_doc = _entry(
                    record,
                    position,
                    item.artifact_ref,
                    working['record_sha256'],
                    include_artifact=True,
                )
                payload = _encode(payload_doc) + b'\n'
                previous_end = 0
            if pending and (
                relative != working['segment_path']
                or len(pending) >= self.max_batch_records
                or pending_bytes + len(payload) > self.max_batch_bytes
            ):
                flush()
            pending.append(payload)
            pending_bytes += len(payload)
            working = {
                'document_type': CURSOR_DOCUMENT_TYPE,
                'schema_version': SCHEMA_VERSION,
                'artifact_ref': item.artifact_ref.as_document(),
                'journal_position': position.as_document(),
                'segment_path': relative,
                'record_start': previous_end,
                'record_end': previous_end + len(payload),
                'record_sha256': payload_doc['sha256'],
            }
            count += 1
        flush()
        return count
