# Publica los hechos durables del Engine como lotes inmutables para otro job.
# El WAL sigue siendo la única autoridad; este módulo no crea un journal adicional.
# Cada archivo tiene identidad derivada del hash del commit y puede reintentarse.
# El cursor se actualiza únicamente después de confirmar el archivo correspondiente.
# Un checkpoint de una revisión anterior no impide exportar commits nuevos de otra revisión.
# Los commits pendientes deben corresponder a la revisión efectiva o se detiene el flujo.

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ada_command_center.alarms.persistence import (
    AlarmArtifactRefSnapshot,
    AlarmPersistence,
    JournalEntry,
    JournalPosition,
)
from atlanticus.state import AtomicJsonStore

DOCUMENT_TYPE = 'ada_command_center_engine_committed_facts_batch'
SCHEMA_VERSION = 1
_CURSOR = 'state/facts-export-cursor.json'


class EngineFactsPublicationError(RuntimeError):
    pass


def _artifact_document(pin: AlarmArtifactRefSnapshot) -> dict[str, object]:
    return pin.as_document()


def _fact_batch(entry: JournalEntry, pin: AlarmArtifactRefSnapshot) -> dict[str, object]:
    record = entry.record
    commit = record.commit
    if (
        commit.alarm_configuration_revision != pin.alarm_configuration_revision
        or commit.tool_registry_revision != pin.confirmed_tool_catalog_revision
    ):
        raise EngineFactsPublicationError(
            'Committed facts do not match the selected EFFECTIVE revision'
        )
    if re.fullmatch(r'sha256:[0-9a-f]{64}', record.record_hash) is None:
        raise EngineFactsPublicationError('Committed record hash is invalid')
    batch = {
        'document_type': DOCUMENT_TYPE,
        'schema_version': SCHEMA_VERSION,
        'batch_id': f"facts-{record.record_hash.removeprefix('sha256:')}",
        'artifact_ref': _artifact_document(pin),
        'journal_position': entry.end.as_document(),
        'commit': commit.as_document(),
        'commit_record_hash': record.record_hash,
        'records': {key: value for key, value in record.records.items() if value},
    }
    batch['sha256'] = _digest(batch)
    return batch


def _digest(document: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode(
            'utf-8'
        )
    ).hexdigest()


@dataclass(slots=True)
class AlarmCommittedFactsExporter:
    root: Path
    source_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.root, Path) or not self.root.is_absolute():
            raise ValueError('Engine output root must be an absolute Path')
        if not isinstance(self.source_key, str) or not self.source_key.strip():
            raise ValueError('Engine output source_key must be non-empty text')

    def initialize_if_needed(
        self, *, context, persistence: AlarmPersistence, pin: AlarmArtifactRefSnapshot
    ) -> bool:
        if not isinstance(persistence, AlarmPersistence):
            raise TypeError('persistence must be AlarmPersistence')
        if not isinstance(pin, AlarmArtifactRefSnapshot) or pin.source_key != self.source_key:
            raise EngineFactsPublicationError('Selected EFFECTIVE source_key does not match output')
        store = AtomicJsonStore(root_path=self.root, max_document_bytes=None)
        if store.read(_CURSOR) is not None:
            return False
        context.assert_lease_current()
        head = persistence.read_head()
        if not head.aligned:
            raise EngineFactsPublicationError('Engine WAL must be recovered before export baseline')
        if persistence.read_durable_records():
            raise EngineFactsPublicationError(
                'Existing committed history requires an explicit initial export baseline'
            )
        with context.fenced_mutation():
            if store.read(_CURSOR) is not None:
                return False
            store.replace(
                _CURSOR,
                {
                    'document_type': 'ada_command_center_engine_facts_export_cursor',
                    'schema_version': SCHEMA_VERSION,
                    'artifact_ref': _artifact_document(pin),
                    'batch_id': None,
                    'batch_sha256': None,
                    'journal_position': (
                        None if head.durable is None else head.durable.as_document()
                    ),
                },
            )
        return True

    def publish_unexported(
        self, *, context, persistence: AlarmPersistence, pin: AlarmArtifactRefSnapshot
    ) -> int:
        if not isinstance(persistence, AlarmPersistence):
            raise TypeError('persistence must be AlarmPersistence')
        if not isinstance(pin, AlarmArtifactRefSnapshot):
            raise TypeError('pin must be AlarmArtifactRefSnapshot')
        if pin.source_key != self.source_key:
            raise EngineFactsPublicationError('Selected EFFECTIVE source_key does not match output')
        store = AtomicJsonStore(root_path=self.root, max_document_bytes=None)
        checkpoint = store.read(_CURSOR)
        if checkpoint is None:
            raise EngineFactsPublicationError('Facts export baseline must be initialized first')
        cursor = self._read_checkpoint(checkpoint, store)
        if not persistence.read_head().aligned:
            raise EngineFactsPublicationError('Engine WAL must be recovered before exporting facts')
        entries = persistence.read_durable_records(after=cursor)
        previous_artifact = checkpoint['artifact_ref']
        if (
            entries
            and previous_artifact != _artifact_document(pin)
            and previous_artifact.get('resolution_key')
            == _artifact_document(pin)['resolution_key']
        ):
            raise EngineFactsPublicationError(
                'Historical commit origin is ambiguous after a same-revision artifact change'
            )
        count = 0
        for entry in entries:
            context.assert_lease_current()
            batch = _fact_batch(entry, pin)
            path = f"facts/{batch['batch_id']}.json"
            with context.fenced_mutation():
                current = store.read(path)
                if current is not None and current != batch:
                    raise EngineFactsPublicationError(
                        'Existing facts batch differs from durable WAL'
                    )
                if current is None:
                    store.replace(path, batch)
                store.replace(
                    _CURSOR,
                    {
                        'document_type': 'ada_command_center_engine_facts_export_cursor',
                        'schema_version': SCHEMA_VERSION,
                        'artifact_ref': _artifact_document(pin),
                        'batch_id': batch['batch_id'],
                        'batch_sha256': batch['sha256'],
                        'journal_position': entry.end.as_document(),
                    },
                )
            count += 1
        return count

    @staticmethod
    def _read_checkpoint(checkpoint: dict, store: AtomicJsonStore) -> JournalPosition | None:
        if (
            checkpoint.get('document_type') != 'ada_command_center_engine_facts_export_cursor'
            or checkpoint.get('schema_version') != SCHEMA_VERSION
        ):
            raise EngineFactsPublicationError('Invalid Engine facts export checkpoint')
        previous = checkpoint.get('artifact_ref')
        if not isinstance(previous, dict) or set(previous) != {
            'source_key', 'result_id', 'manifest_sha256', 'resolution_key'
        }:
            raise EngineFactsPublicationError('Invalid facts export artifact reference')
        batch_id = checkpoint.get('batch_id')
        if batch_id is None:
            if checkpoint.get('batch_sha256') is not None:
                raise EngineFactsPublicationError('Invalid initial facts export checkpoint')
            position = checkpoint.get('journal_position')
            try:
                return None if position is None else JournalPosition.from_document(position)
            except (ValueError, TypeError) as error:
                raise EngineFactsPublicationError(
                    'Invalid initial facts export position'
                ) from error
        if not isinstance(batch_id, str) or re.fullmatch(r'facts-[0-9a-f]{64}', batch_id) is None:
            raise EngineFactsPublicationError('Invalid last exported facts batch identity')
        last = store.read(f'facts/{batch_id}.json')
        if (
            last is None
            or last.get('batch_id') != batch_id
            or last.get('artifact_ref') != previous
            or last.get('journal_position') != checkpoint.get('journal_position')
            or not isinstance(checkpoint.get('batch_sha256'), str)
            or last.get('sha256') != checkpoint['batch_sha256']
            or _digest({key: value for key, value in last.items() if key != 'sha256'})
            != last.get('sha256')
        ):
            raise EngineFactsPublicationError(
                'Last exported facts batch is unavailable or invalid'
            )
        try:
            return JournalPosition.from_document(checkpoint['journal_position'])
        except (KeyError, ValueError, TypeError) as error:
            raise EngineFactsPublicationError('Invalid facts export journal position') from error
