from __future__ import annotations

import hashlib
import json
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
from atlanticus.state import AtomicJsonStore

DOCUMENT_TYPE = 'ada_command_center_engine_committed_facts_batch'
CURSOR_DOCUMENT_TYPE = 'ada_command_center_engine_facts_export_cursor'
SCHEMA_VERSION = 3
_CURSOR = 'state/facts-export-cursor.json'
_BATCH_PATTERN = re.compile(r'facts-[0-9a-f]{64}')
_RECORD_HASH_PATTERN = re.compile(r'sha256:[0-9a-f]{64}')
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


def _digest(document: dict[str, object]) -> str:
    payload = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _checkpoint_document(
    *,
    artifact_ref: dict[str, object] | None,
    batch_id: str | None,
    batch_sha256: str | None,
    position: JournalPosition | None,
) -> dict[str, object]:
    return {
        'document_type': CURSOR_DOCUMENT_TYPE,
        'schema_version': SCHEMA_VERSION,
        'artifact_ref': artifact_ref,
        'batch_id': batch_id,
        'batch_sha256': batch_sha256,
        'journal_position': None if position is None else position.as_document(),
    }


def _fact_batch(
    *,
    record: EngineCommitRecord,
    position: JournalPosition,
    artifact_ref: AlarmArtifactRefSnapshot,
    previous_batch: dict[str, str] | None,
) -> dict[str, object]:
    if (
        record.commit.alarm_configuration_revision != artifact_ref.alarm_configuration_revision
        or record.commit.tool_registry_revision != artifact_ref.confirmed_tool_catalog_revision
    ):
        raise EngineFactsPublicationError('Committed facts do not match their durable artifact')
    if _RECORD_HASH_PATTERN.fullmatch(record.record_hash) is None:
        raise EngineFactsPublicationError('Committed record hash is invalid')
    unknown = set(record.records) - _RECORD_COLLECTIONS
    if unknown:
        raise EngineFactsPublicationError('Committed facts contain unsupported record collections')
    document: dict[str, object] = {
        'document_type': DOCUMENT_TYPE,
        'schema_version': SCHEMA_VERSION,
        'batch_id': f'facts-{record.record_hash.removeprefix("sha256:")}',
        'artifact_ref': artifact_ref.as_document(),
        'journal_position': position.as_document(),
        'commit': record.commit.as_document(),
        'commit_record_hash': record.record_hash,
        'previous_batch': previous_batch,
        'records': {name: values for name, values in record.records.items() if values},
    }
    document['sha256'] = _digest(document)
    return document


@dataclass(slots=True)
class AlarmCommittedFactsExporter:
    root: Path
    source_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.root, Path) or not self.root.is_absolute():
            raise ValueError('Engine output root must be an absolute Path')
        if (
            not isinstance(self.source_key, str)
            or not self.source_key
            or self.source_key != self.source_key.strip()
        ):
            raise ValueError('Engine output source_key must be non-empty text')

    def initialize_if_needed(
        self, *, context: FactsExportContext, persistence: AlarmPersistence
    ) -> bool:
        if not isinstance(persistence, AlarmPersistence):
            raise TypeError('persistence must be AlarmPersistence')
        store = AtomicJsonStore(root_path=self.root, max_document_bytes=None)
        checkpoint = store.read(_CURSOR)
        if checkpoint is not None:
            self._read_checkpoint(checkpoint, store)
            return False
        facts_root = self.root / 'facts'
        if facts_root.exists() and any(facts_root.iterdir()):
            raise EngineFactsPublicationError('Existing facts files require controlled migration')
        context.assert_lease_current()
        persistence.read_durable_provenance()
        with context.fenced_mutation():
            checkpoint = store.read(_CURSOR)
            if checkpoint is not None:
                self._read_checkpoint(checkpoint, store)
                return False
            if facts_root.exists() and any(facts_root.iterdir()):
                raise EngineFactsPublicationError(
                    'Existing facts files require controlled migration'
                )
            store.replace(
                _CURSOR,
                _checkpoint_document(
                    artifact_ref=None, batch_id=None, batch_sha256=None, position=None
                ),
            )
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
        cursor = self._read_checkpoint(checkpoint, store)
        context.assert_lease_current()
        entries = persistence.read_durable_provenance(after=cursor)
        previous_batch = (
            None
            if checkpoint['batch_id'] is None
            else {'batch_id': checkpoint['batch_id'], 'sha256': checkpoint['batch_sha256']}
        )
        count = 0
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
            batch = _fact_batch(
                record=record,
                position=position,
                artifact_ref=item.artifact_ref,
                previous_batch=previous_batch,
            )
            batch_path = f'facts/{batch["batch_id"]}.json'
            updated_checkpoint = _checkpoint_document(
                artifact_ref=item.artifact_ref.as_document(),
                batch_id=batch['batch_id'],
                batch_sha256=batch['sha256'],
                position=position,
            )
            with context.fenced_mutation():
                if store.read(_CURSOR) != checkpoint:
                    raise EngineFactsPublicationError(
                        'Facts export checkpoint changed during publication'
                    )
                current = store.read(batch_path)
                if current is not None and current != batch:
                    raise EngineFactsPublicationError(
                        'Existing facts batch differs from durable WAL'
                    )
                if current is None:
                    store.replace(batch_path, batch)
                store.replace(_CURSOR, updated_checkpoint)
            checkpoint = updated_checkpoint
            previous_batch = {'batch_id': batch['batch_id'], 'sha256': batch['sha256']}
            count += 1
        return count

    @staticmethod
    def _read_checkpoint(checkpoint: dict, store: AtomicJsonStore) -> JournalPosition | None:
        if (
            not isinstance(checkpoint, dict)
            or set(checkpoint)
            != {
                'document_type',
                'schema_version',
                'artifact_ref',
                'batch_id',
                'batch_sha256',
                'journal_position',
            }
            or checkpoint['document_type'] != CURSOR_DOCUMENT_TYPE
            or checkpoint['schema_version'] != SCHEMA_VERSION
        ):
            raise EngineFactsPublicationError('Facts export checkpoint requires the v3 contract')
        batch_id = checkpoint['batch_id']
        if batch_id is None:
            if any(
                checkpoint[key] is not None
                for key in ('artifact_ref', 'batch_sha256', 'journal_position')
            ):
                raise EngineFactsPublicationError('Initial facts export checkpoint is invalid')
            return None
        if not isinstance(batch_id, str) or _BATCH_PATTERN.fullmatch(batch_id) is None:
            raise EngineFactsPublicationError('Last exported facts batch identity is invalid')
        position_document = checkpoint['journal_position']
        try:
            position = JournalPosition.from_document(position_document)
        except (TypeError, ValueError, KeyError, AlarmPersistenceCorruptionError) as error:
            raise EngineFactsPublicationError('Facts export journal position is invalid') from error
        previous = checkpoint['artifact_ref']
        try:
            artifact = AlarmArtifactRefSnapshot.from_document(previous)
        except (TypeError, ValueError, KeyError, AlarmPersistenceCorruptionError) as error:
            raise EngineFactsPublicationError(
                'Facts export artifact reference is invalid'
            ) from error
        batch = store.read(f'facts/{batch_id}.json')
        if (
            not isinstance(batch, dict)
            or batch.get('document_type') != DOCUMENT_TYPE
            or batch.get('schema_version') != SCHEMA_VERSION
            or batch.get('batch_id') != batch_id
            or batch.get('journal_position') != position.as_document()
            or batch.get('artifact_ref') != artifact.as_document()
            or not isinstance(checkpoint['batch_sha256'], str)
            or batch.get('sha256') != checkpoint['batch_sha256']
            or _digest({key: value for key, value in batch.items() if key != 'sha256'})
            != batch.get('sha256')
        ):
            raise EngineFactsPublicationError('Last exported facts batch is unavailable or invalid')
        return position
