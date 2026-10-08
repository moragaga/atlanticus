# Publicador de CURRENT durable: solo representa estado confirmado en WAL y snapshots.
# No obtiene entradas operacionales, no recalcula prioridad y no modifica FACTS.
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ada.alarms.persistence.operational import (
    GROUP_RUNTIME_SNAPSHOT_V3_SCHEMA_VERSION,
    AlarmArtifactRefSnapshot,
    AlarmPersistence,
    AlarmPersistenceCorruptionError,
    GroupRuntimeSnapshot,
    JournalPosition,
)
from atlanticus.state import AtomicJsonStore

# Identidad y versión propias, independientes del CURRENT histórico de Web.
DOCUMENT_TYPE = 'ada_alarm_engine_durable_current_state'
SCHEMA_VERSION = 1
_LATEST = 'current/durable-latest.json'


class EngineDurableCurrentPublicationError(RuntimeError):
    pass


class DurableCurrentContext(Protocol):
    def assert_lease_current(self) -> None: ...

    def fenced_mutation(self): ...


# Canonización estable para integridad; el hash excluye su propio campo.
def _digest(document: dict[str, object]) -> str:
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


# Una posición se ordena por segmento y desplazamiento, nunca por timestamp de publicación.
def _position_key(position: JournalPosition) -> tuple[str, int]:
    return position.segment_id, position.byte_offset


# La lectura EFFECTIVE valida la cadena WAL y la coherencia de snapshots.
# Si falta autoridad o hay divergencia de revisiones, no se publica un estado engañoso.
def _read_authority(
    *, persistence: AlarmPersistence, source_key: str
) -> tuple[AlarmArtifactRefSnapshot, JournalPosition, list[dict[str, object]]]:
    effective = persistence.read_effective_head()
    if effective is None:
        raise EngineDurableCurrentPublicationError(
            'EFFECTIVE is unavailable; cannot publish CURRENT'
        )
    artifact = effective.target_artifact_ref
    if artifact.source_key != source_key:
        raise EngineDurableCurrentPublicationError('EFFECTIVE source_key differs from CURRENT')
    head = persistence.read_head()
    if not head.aligned or head.durable is None:
        raise EngineDurableCurrentPublicationError('CURRENT requires an aligned durable journal')
    snapshots = persistence.list_snapshots()
    # Los snapshots vacíos conservan el commit que cerró un grupo: no se descartan.
    groups = []
    seen: set[str] = set()
    for snapshot in snapshots:
        document = snapshot.as_document()
        if document['snapshot_schema_version'] != GROUP_RUNTIME_SNAPSHOT_V3_SCHEMA_VERSION:
            raise EngineDurableCurrentPublicationError(
                'CURRENT requires lossless group snapshot v3'
            )
        group = snapshot.priority_group
        if group in seen:
            raise EngineDurableCurrentPublicationError('Duplicate priority_group in snapshots')
        seen.add(group)
        if document['state_basis'] != {
            'alarm_configuration_revision': artifact.alarm_configuration_revision,
            'tool_registry_revision': artifact.confirmed_tool_catalog_revision,
        }:
            raise EngineDurableCurrentPublicationError('Snapshot revisions differ from EFFECTIVE')
        groups.append(document)
    if persistence.read_head() != head:
        raise EngineDurableCurrentPublicationError('Durable journal changed during CURRENT read')
    return artifact, head.durable, sorted(groups, key=lambda value: value['priority_group'])


# Se comprueba cada archivo existente antes de actualizarlo; no se usa best effort.
def _validate_document(document: object) -> tuple[AlarmArtifactRefSnapshot, JournalPosition]:
    if not isinstance(document, dict) or set(document) != {
        'document_type', 'schema_version', 'artifact_ref', 'journal_position', 'state', 'sha256'
    }:
        raise EngineDurableCurrentPublicationError('Existing CURRENT document has invalid fields')
    if document['document_type'] != DOCUMENT_TYPE or document['schema_version'] != SCHEMA_VERSION:
        raise EngineDurableCurrentPublicationError('Existing CURRENT requires durable schema v1')
    if not isinstance(document['sha256'], str) or len(document['sha256']) != 64:
        raise EngineDurableCurrentPublicationError('Existing CURRENT digest is invalid')
    if (
        _digest({key: value for key, value in document.items() if key != 'sha256'})
        != document['sha256']
    ):
        raise EngineDurableCurrentPublicationError('Existing CURRENT integrity check failed')
    state = document['state']
    if not isinstance(state, dict) or set(state) != {'resolution_key', 'groups'}:
        raise EngineDurableCurrentPublicationError('Existing CURRENT state is invalid')
    if not isinstance(state['groups'], list):
        raise EngineDurableCurrentPublicationError('Existing CURRENT groups must be an array')
    try:
        artifact = AlarmArtifactRefSnapshot.from_document(document['artifact_ref'])
        position = JournalPosition.from_document(document['journal_position'])
        if state['resolution_key'] != artifact.as_document()['resolution_key']:
            raise ValueError('CURRENT resolution_key differs from artifact_ref')
        groups = [GroupRuntimeSnapshot.from_document(item) for item in state['groups']]
    except (TypeError, ValueError, KeyError, AlarmPersistenceCorruptionError) as error:
        raise EngineDurableCurrentPublicationError(
            'Existing CURRENT has invalid durable contracts'
        ) from error
    if any(
        group.as_document()['snapshot_schema_version'] != GROUP_RUNTIME_SNAPSHOT_V3_SCHEMA_VERSION
        or group.as_document()['state_basis'] != {
            'alarm_configuration_revision': artifact.alarm_configuration_revision,
            'tool_registry_revision': artifact.confirmed_tool_catalog_revision,
        }
        for group in groups
    ):
        raise EngineDurableCurrentPublicationError(
            'Existing CURRENT snapshots differ from EFFECTIVE'
        )
    keys = [group.priority_group for group in groups]
    if keys != sorted(set(keys)):
        raise EngineDurableCurrentPublicationError(
            'Existing CURRENT groups are not unique and sorted'
        )
    return artifact, position


# El componente no posee clientes globales ni ciclo de vida. El contexto aporta fencing.
@dataclass(slots=True)
class AlarmDurableCurrentPublisher:
    root: Path
    source_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.root, Path) or not self.root.is_absolute():
            raise ValueError('CURRENT output root must be an absolute Path')
        if (
            not isinstance(self.source_key, str)
            or not self.source_key
            or self.source_key.strip() != self.source_key
        ):
            raise ValueError('CURRENT source_key must be non-empty text')

    def publish(
        self, *, context: DurableCurrentContext, persistence: AlarmPersistence
    ) -> bool:
        if not isinstance(persistence, AlarmPersistence):
            raise TypeError('persistence must be AlarmPersistence')
        context.assert_lease_current()
        artifact, position, groups = _read_authority(
            persistence=persistence, source_key=self.source_key
        )
        document: dict[str, object] = {
            'document_type': DOCUMENT_TYPE,
            'schema_version': SCHEMA_VERSION,
            'artifact_ref': artifact.as_document(),
            'journal_position': position.as_document(),
            'state': {
                'resolution_key': artifact.as_document()['resolution_key'],
                'groups': groups,
            },
        }
        document['sha256'] = _digest(document)
        store = AtomicJsonStore(root_path=self.root, max_document_bytes=None)
        # Dentro del fencing, confirmar de nuevo exactamente el mismo estado de autoridad.
        with context.fenced_mutation():
            context.assert_lease_current()
            verified_artifact, verified_position, verified_groups = _read_authority(
                persistence=persistence, source_key=self.source_key
            )
            if (verified_artifact, verified_position, verified_groups) != (
                artifact, position, groups
            ):
                raise EngineDurableCurrentPublicationError(
                    'Durable authority changed during CURRENT publication'
                )
            previous = store.read(_LATEST)
            if previous is not None:
                previous_artifact, previous_position = _validate_document(previous)
                if previous_artifact.source_key != self.source_key:
                    raise EngineDurableCurrentPublicationError(
                        'Existing CURRENT source_key differs'
                    )
                # Evitar regresiones incluso si un documento previo es íntegro.
                previous_key = _position_key(previous_position)
                next_key = _position_key(position)
                if previous_key > next_key:
                    raise EngineDurableCurrentPublicationError('CURRENT cannot move backward')
                if previous_key == next_key:
                    if previous_position != position or previous != document:
                        raise EngineDurableCurrentPublicationError(
                            'Conflicting CURRENT states share a durable journal position'
                        )
                    return False
            store.replace(_LATEST, document)
        return True
