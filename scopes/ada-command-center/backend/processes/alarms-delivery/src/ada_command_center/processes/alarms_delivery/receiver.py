from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ada_command_center.alarms.materialization.local_reader import (
    LocalAlarmMaterializationReader,
    materialization_root,
)
from ada_command_center.alarms.persistence import (
    AlarmArtifactRefSnapshot,
    AlarmEffectiveConfigurationHead,
    EngineCommitMetadata,
    JournalPosition,
)
from atlanticus.state import AtomicJsonStore

_CURRENT_TYPE = 'ada_command_center_engine_resolved_current_state'
_FACTS_TYPE = 'ada_command_center_engine_committed_facts_batch'
_EXPORT_CURSOR_TYPE = 'ada_command_center_engine_facts_export_cursor'
_CONSUMER_CURSOR_TYPE = 'ada_command_center_delivery_facts_receipt_cursor'
_CURRENT_PATH = 'current/latest.json'
_EXPORT_CURSOR_PATH = 'state/facts-export-cursor.json'
_CONSUMER_CURSOR_PATH = 'state/facts-consumption-cursor.json'
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_BATCH_ID = re.compile(r'facts-[0-9a-f]{64}\Z')
_RECORD_COLLECTIONS = frozenset(
    {
        'assignment_changes',
        'deactivation_effects',
        'deactivation_requests',
        'episode_changes',
        'evidence_records',
        'input_receipts',
        'journey_events',
        'management_effects',
        'occurrence_changes',
    }
)


class AlarmDeliveryInputError(RuntimeError):
    pass


def _hash(document: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode(
            'utf-8'
        )
    ).hexdigest()


def _utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise AlarmDeliveryInputError('Publication timestamp must be ISO-8601 UTC text')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise AlarmDeliveryInputError('Publication timestamp is invalid') from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise AlarmDeliveryInputError('Publication timestamp must be timezone-aware UTC')
    return parsed.astimezone(UTC)


def _verify_digest(document: dict[str, Any]) -> None:
    digest = document.get('sha256')
    if not isinstance(digest, str) or not _HASH.fullmatch(digest):
        raise AlarmDeliveryInputError('Publication checksum is missing or invalid')
    if _hash({key: value for key, value in document.items() if key != 'sha256'}) != digest:
        raise AlarmDeliveryInputError('Publication checksum mismatch')


def _reference(value: object) -> AlarmArtifactRefSnapshot:
    if not isinstance(value, dict):
        raise AlarmDeliveryInputError('Publication artifact reference is invalid')
    try:
        return AlarmArtifactRefSnapshot.from_document(value)
    except (TypeError, ValueError, RuntimeError) as error:
        raise AlarmDeliveryInputError('Publication artifact reference is invalid') from error


def _position(value: object) -> JournalPosition:
    if not isinstance(value, dict):
        raise AlarmDeliveryInputError('Publication journal position is invalid')
    try:
        return JournalPosition.from_document(value)
    except (TypeError, ValueError, RuntimeError) as error:
        raise AlarmDeliveryInputError('Publication journal position is invalid') from error


def _position_order(value: JournalPosition) -> tuple[str, int]:
    return value.segment_id, value.byte_offset


def _current(document: dict[str, Any], *, source_key: str) -> AlarmArtifactRefSnapshot:
    if set(document) != {'document_type', 'schema_version', 'artifact_ref', 'state', 'sha256'}:
        raise AlarmDeliveryInputError('Current publication has unsupported fields')
    if document['document_type'] != _CURRENT_TYPE or document['schema_version'] != 1:
        raise AlarmDeliveryInputError('Current publication contract is unsupported')
    _verify_digest(document)
    pin = _reference(document['artifact_ref'])
    if pin.source_key != source_key:
        raise AlarmDeliveryInputError('Current publication source is invalid')
    state = document['state']
    if not isinstance(state, dict) or set(state) != {'resolution_key', 'as_of', 'alarms'}:
        raise AlarmDeliveryInputError('Current state has unsupported fields')
    if state['resolution_key'] != pin.as_document()['resolution_key']:
        raise AlarmDeliveryInputError('Current state configuration does not match publication')
    as_of = _utc(state['as_of'])
    alarms = state['alarms']
    if not isinstance(alarms, list):
        raise AlarmDeliveryInputError('Current occurrences must be an array')
    seen = set()
    for alarm in alarms:
        if not isinstance(alarm, dict) or set(alarm) != {
            'identity',
            'occurrence_id',
            'episode_id',
            'started_at',
            'evaluation',
            'priority',
            'technical_hold',
            'management_cycle',
            'management_effect',
            'deactivation_effect',
            'pending_deactivation_request',
            'assignments',
            'pending_assignments',
        }:
            raise AlarmDeliveryInputError('Current occurrence has unsupported fields')
        identity = alarm['identity']
        if not isinstance(identity, str) or not identity.strip() or identity in seen:
            raise AlarmDeliveryInputError('Current occurrence identities must be unique')
        seen.add(identity)
        if not all(
            isinstance(alarm[key], str) and alarm[key] for key in ('occurrence_id', 'episode_id')
        ):
            raise AlarmDeliveryInputError('Current occurrence identifiers are invalid')
        if _utc(alarm['started_at']) > as_of:
            raise AlarmDeliveryInputError('Current occurrence starts after publication')
        evaluation = alarm['evaluation']
        if not isinstance(evaluation, dict) or set(evaluation) != {
            'status',
            'evaluated_at',
            'evidence',
            'error',
        }:
            raise AlarmDeliveryInputError('Current evaluation is invalid')
        if evaluation['status'] not in {'ACTIVE', 'INACTIVE', 'ERROR'}:
            raise AlarmDeliveryInputError('Current evaluation status is unsupported')
        if _utc(evaluation['evaluated_at']) != as_of:
            raise AlarmDeliveryInputError('Current evaluation and snapshot time differ')
        if evaluation['status'] == 'ERROR':
            if not isinstance(evaluation['error'], dict) or evaluation['evidence'] is not None:
                raise AlarmDeliveryInputError('Current ERROR evaluation content is invalid')
        elif evaluation['error'] is not None:
            raise AlarmDeliveryInputError('Current physical evaluation must not contain error')
        priority = alarm['priority']
        if not isinstance(priority, dict) or set(priority) != {'disposition', 'blockers'}:
            raise AlarmDeliveryInputError('Current priority is invalid')
        if priority['disposition'] not in {
            'PREDOMINANT',
            'DEACTIVATED',
            'ECLIPSED',
            'CASCADE_SUPPRESSED',
        } or not isinstance(priority['blockers'], list):
            raise AlarmDeliveryInputError('Current priority disposition is invalid')
        if any(not isinstance(key, str) or not key for key in priority['blockers']):
            raise AlarmDeliveryInputError('Current priority blockers are invalid')
        for key in ('assignments', 'pending_assignments'):
            if not isinstance(alarm[key], list):
                raise AlarmDeliveryInputError('Current assignments must be arrays')
        management = alarm['management_cycle']
        if management is not None and (
            isinstance(management, bool) or not isinstance(management, int) or management < 0
        ):
            raise AlarmDeliveryInputError('Current management cycle is invalid')
        for key in (
            'technical_hold',
            'management_effect',
            'deactivation_effect',
            'pending_deactivation_request',
        ):
            if alarm[key] is not None and not isinstance(alarm[key], dict):
                raise AlarmDeliveryInputError(f'Current {key} is invalid')
    return pin


def _facts(
    document: dict[str, Any], *, source_key: str
) -> tuple[AlarmArtifactRefSnapshot, JournalPosition]:
    if set(document) != {
        'document_type',
        'schema_version',
        'batch_id',
        'artifact_ref',
        'journal_position',
        'commit',
        'commit_record_hash',
        'previous_batch',
        'records',
        'sha256',
    }:
        raise AlarmDeliveryInputError('Facts batch has unsupported fields')
    if document['document_type'] != _FACTS_TYPE or document['schema_version'] != 2:
        raise AlarmDeliveryInputError('Facts batch contract is unsupported')
    _verify_digest(document)
    previous = document['previous_batch']
    if previous is not None and (
        not isinstance(previous, dict)
        or set(previous) != {'batch_id', 'sha256'}
        or not isinstance(previous['batch_id'], str)
        or not _BATCH_ID.fullmatch(previous['batch_id'])
        or not isinstance(previous['sha256'], str)
        or not _HASH.fullmatch(previous['sha256'])
    ):
        raise AlarmDeliveryInputError('Facts previous batch reference is invalid')
    batch_id = document['batch_id']
    if not isinstance(batch_id, str) or not _BATCH_ID.fullmatch(batch_id):
        raise AlarmDeliveryInputError('Facts batch identity is invalid')
    record_hash = document['commit_record_hash']
    if (
        not isinstance(record_hash, str)
        or re.fullmatch(r'sha256:[0-9a-f]{64}', record_hash) is None
        or batch_id != f'facts-{record_hash.removeprefix("sha256:")}'
    ):
        raise AlarmDeliveryInputError('Facts batch and commit record identity differ')
    pin = _reference(document['artifact_ref'])
    if pin.source_key != source_key:
        raise AlarmDeliveryInputError('Facts batch source is invalid')
    position = _position(document['journal_position'])
    commit_document = document['commit']
    if not isinstance(commit_document, dict):
        raise AlarmDeliveryInputError('Facts commit metadata is invalid')
    try:
        commit = EngineCommitMetadata.from_document(commit_document)
    except (TypeError, ValueError, RuntimeError) as error:
        raise AlarmDeliveryInputError('Facts commit metadata is invalid') from error
    if position.commit_id != commit.commit_id:
        raise AlarmDeliveryInputError('Facts journal position does not match commit')
    if (
        commit.alarm_configuration_revision != pin.alarm_configuration_revision
        or commit.tool_registry_revision != pin.confirmed_tool_catalog_revision
    ):
        raise AlarmDeliveryInputError('Facts commit configuration does not match artifact')
    records = document['records']
    if not isinstance(records, dict) or set(records) - _RECORD_COLLECTIONS:
        raise AlarmDeliveryInputError('Facts records contain unsupported collections')
    if any(
        not isinstance(items, list)
        or not items
        or not all(isinstance(item, dict) for item in items)
        for items in records.values()
    ):
        raise AlarmDeliveryInputError('Facts records must contain non-empty object arrays')
    return pin, position


@dataclass(frozen=True, slots=True)
class DeliveryInputCycleResult:
    current_status: str
    staged_facts: int
    last_facts_batch_id: str | None


@dataclass(slots=True)
class LocalAlarmDeliveryReceiver:
    volume_path: Path
    source_key: str
    max_facts_per_iteration: int = 100

    def __post_init__(self) -> None:
        if not isinstance(self.volume_path, Path) or not self.volume_path.is_absolute():
            raise ValueError('VOLUMEN_PATH must be an absolute Path')
        if (
            not isinstance(self.source_key, str)
            or not self.source_key
            or self.source_key != self.source_key.strip()
        ):
            raise ValueError('ALARM_CONFIGURATION_SOURCE_KEY must be non-empty text')
        if (
            isinstance(self.max_facts_per_iteration, bool)
            or not isinstance(self.max_facts_per_iteration, int)
            or self.max_facts_per_iteration <= 0
        ):
            raise ValueError('max_facts_per_iteration must be a positive integer')

    @property
    def engine_root(self) -> Path:
        return self.volume_path / 'ada-command-center' / 'alarms' / 'runtime' / 'output'

    @property
    def inbox_root(self) -> Path:
        return self.volume_path / 'ada-command-center' / 'alarms' / 'delivery' / 'input'

    @property
    def alarms_root(self) -> Path:
        return self.volume_path / 'ada-command-center' / 'alarms'

    def recover(self, _context: object) -> None:
        inbox = AtomicJsonStore(root_path=self.inbox_root, max_document_bytes=None)
        checkpoint = inbox.read(_CONSUMER_CURSOR_PATH)
        if checkpoint is not None:
            self._verify_received_chain(checkpoint, inbox)
        current = inbox.read(_CURRENT_PATH)
        if current is not None:
            _current(current, source_key=self.source_key)

    def consume(self, context: object) -> DeliveryInputCycleResult:
        context.assert_lease_current()
        inbox = AtomicJsonStore(root_path=self.inbox_root, max_document_bytes=None)
        engine = AtomicJsonStore(root_path=self.engine_root, max_document_bytes=None)
        current_status = self._stage_current(context, inbox, engine)
        count, last = self._stage_facts(context, inbox, engine)
        return DeliveryInputCycleResult(
            current_status=current_status,
            staged_facts=count,
            last_facts_batch_id=last,
        )

    def _verify_received_chain(self, checkpoint: dict[str, Any], inbox: AtomicJsonStore) -> None:
        cursor, position = self._consumer_cursor(checkpoint, inbox)
        document = inbox.read(f'facts/{cursor["batch_id"]}.json')
        if document is None:
            raise AlarmDeliveryInputError('Last received facts batch disappeared during recovery')
        seen: set[str] = set()
        while True:
            batch_id = document['batch_id']
            if batch_id in seen:
                raise AlarmDeliveryInputError('Delivery receipt chain contains a cycle')
            seen.add(batch_id)
            previous = document['previous_batch']
            if previous is None:
                return
            predecessor = inbox.read(f'facts/{previous["batch_id"]}.json')
            if predecessor is None:
                raise AlarmDeliveryInputError('Delivery receipt chain is missing a prior batch')
            _, before = _facts(predecessor, source_key=self.source_key)
            if (
                predecessor['batch_id'] != previous['batch_id']
                or predecessor['sha256'] != previous['sha256']
                or _position_order(before) >= _position_order(position)
            ):
                raise AlarmDeliveryInputError('Delivery receipt chain has invalid predecessor')
            document = predecessor
            position = before

    def _effective(self) -> AlarmEffectiveConfigurationHead | None:
        document = AtomicJsonStore(root_path=self.alarms_root, max_document_bytes=None).read(
            'runtime/state/effective-head.json'
        )
        if document is None:
            return None
        try:
            head = AlarmEffectiveConfigurationHead.from_document(document)
        except (TypeError, ValueError, RuntimeError) as error:
            raise AlarmDeliveryInputError('Engine EFFECTIVE head projection is invalid') from error
        if head.target_artifact_ref.source_key != self.source_key:
            raise AlarmDeliveryInputError('Engine EFFECTIVE source differs from Delivery source')
        return head

    def _exact(self, pin: AlarmArtifactRefSnapshot) -> None:
        try:
            result = LocalAlarmMaterializationReader(
                root=materialization_root(self.volume_path)
            ).read_exact_ready(
                source_key=pin.source_key,
                result_id=pin.result_id,
                manifest_sha256=pin.manifest_sha256,
            )
        except (TypeError, ValueError, OSError, RuntimeError) as error:
            raise AlarmDeliveryInputError('Exact Delivery configuration is unavailable') from error
        expected = pin.as_document()['resolution_key']
        runtime = result.runtime.resolution_key
        delivery = result.delivery.resolution_key
        if (
            result.result_id != pin.result_id
            or result.manifest_sha256 != pin.manifest_sha256
            or {
                'alarm_configuration_revision': runtime.alarm_configuration_revision,
                'confirmed_tool_catalog_revision': runtime.confirmed_tool_catalog_revision,
            }
            != expected
            or {
                'alarm_configuration_revision': delivery.alarm_configuration_revision,
                'confirmed_tool_catalog_revision': delivery.confirmed_tool_catalog_revision,
            }
            != expected
        ):
            raise AlarmDeliveryInputError('Delivery configuration does not match artifact')

    def _stage_current(
        self, context: object, inbox: AtomicJsonStore, engine: AtomicJsonStore
    ) -> str:
        head = self._effective()
        if head is None:
            return 'WAITING_EFFECTIVE'
        document = engine.read(_CURRENT_PATH)
        if document is None:
            return 'WAITING_CURRENT'
        pin = _current(document, source_key=self.source_key)
        if pin != head.target_artifact_ref:
            return 'WAITING_CURRENT'
        self._exact(pin)
        if self._effective() != head:
            return 'EFFECTIVE_CHANGED'
        staged = inbox.read(_CURRENT_PATH)
        if staged is not None:
            _current(staged, source_key=self.source_key)
            old_at = _utc(staged['state']['as_of'])
            new_at = _utc(document['state']['as_of'])
            if old_at > new_at:
                return 'STALE_SOURCE'
            if old_at == new_at:
                if staged != document:
                    raise AlarmDeliveryInputError('Different current states share publication time')
                return 'CURRENT_UNCHANGED'
        context.assert_lease_current()
        with context.fenced_mutation():
            if self._effective() != head:
                return 'EFFECTIVE_CHANGED'
            inbox.replace(_CURRENT_PATH, document)
        return 'CURRENT_STAGED'

    def _producer_cursor(
        self, engine: AtomicJsonStore
    ) -> tuple[dict[str, Any], JournalPosition] | None:
        cursor = engine.read(_EXPORT_CURSOR_PATH)
        if cursor is None:
            return None
        if (
            set(cursor)
            != {
                'document_type',
                'schema_version',
                'artifact_ref',
                'batch_id',
                'batch_sha256',
                'journal_position',
            }
            or cursor['document_type'] != _EXPORT_CURSOR_TYPE
            or cursor['schema_version'] != 2
        ):
            raise AlarmDeliveryInputError('Engine facts export cursor is invalid')
        batch_id = cursor['batch_id']
        if batch_id is None:
            if cursor['batch_sha256'] is not None:
                raise AlarmDeliveryInputError('Initial Engine facts export cursor is invalid')
            pin = _reference(cursor['artifact_ref'])
            if pin.source_key != self.source_key:
                raise AlarmDeliveryInputError(
                    'Initial Engine facts export cursor source is invalid'
                )
            if cursor['journal_position'] is not None:
                _position(cursor['journal_position'])
            return None
        if not isinstance(batch_id, str) or not _BATCH_ID.fullmatch(batch_id):
            raise AlarmDeliveryInputError('Engine facts export cursor batch identity is invalid')
        source = engine.read(f'facts/{batch_id}.json')
        if source is None:
            raise AlarmDeliveryInputError('Engine last exported facts batch is unavailable')
        _, position = _facts(source, source_key=self.source_key)
        if (
            source['batch_id'] != batch_id
            or source['artifact_ref'] != cursor['artifact_ref']
            or source['sha256'] != cursor['batch_sha256']
            or source['journal_position'] != cursor['journal_position']
        ):
            raise AlarmDeliveryInputError('Engine facts export cursor differs from last batch')
        return cursor, position

    def _consumer_cursor(
        self, cursor: dict[str, Any], inbox: AtomicJsonStore
    ) -> tuple[dict[str, Any], JournalPosition]:
        if (
            set(cursor)
            != {
                'document_type',
                'schema_version',
                'artifact_ref',
                'batch_id',
                'batch_sha256',
                'journal_position',
            }
            or cursor['document_type'] != _CONSUMER_CURSOR_TYPE
            or cursor['schema_version'] != 2
        ):
            raise AlarmDeliveryInputError('Delivery facts receipt cursor is invalid')
        batch_id = cursor['batch_id']
        if not isinstance(batch_id, str) or not _BATCH_ID.fullmatch(batch_id):
            raise AlarmDeliveryInputError('Delivery facts receipt cursor batch identity is invalid')
        received = inbox.read(f'facts/{batch_id}.json')
        if received is None:
            raise AlarmDeliveryInputError(
                'Last received facts batch is missing from Delivery inbox'
            )
        _, position = _facts(received, source_key=self.source_key)
        if (
            received['batch_id'] != batch_id
            or received['artifact_ref'] != cursor['artifact_ref']
            or received['sha256'] != cursor['batch_sha256']
            or received['journal_position'] != cursor['journal_position']
        ):
            raise AlarmDeliveryInputError('Delivery facts receipt cursor differs from staged batch')
        return cursor, position

    def _stage_facts(
        self, context: object, inbox: AtomicJsonStore, engine: AtomicJsonStore
    ) -> tuple[int, str | None]:
        previous = inbox.read(_CONSUMER_CURSOR_PATH)
        consumer = None if previous is None else self._consumer_cursor(previous, inbox)
        producer = self._producer_cursor(engine)
        if producer is None:
            if consumer is not None:
                raise AlarmDeliveryInputError('Engine export cursor disappeared after consumption')
            if self._fact_files():
                raise AlarmDeliveryInputError(
                    'Facts batches exist without a committed export cursor'
                )
            return 0, None
        producer_cursor, producer_position = producer
        if consumer is not None and _position_order(consumer[1]) > _position_order(
            producer_position
        ):
            raise AlarmDeliveryInputError('Delivery consumption is ahead of Engine export')
        if consumer is not None and consumer[1] == producer_position:
            if (
                consumer[0]['batch_id'] != producer_cursor['batch_id']
                or consumer[0]['batch_sha256'] != producer_cursor['batch_sha256']
            ):
                raise AlarmDeliveryInputError(
                    'Same exported position has conflicting batch identities'
                )
            return 0, consumer[0]['batch_id']
        pending: list[tuple[JournalPosition, dict[str, Any]]] = []
        for path in self._fact_files():
            if path.is_symlink():
                raise AlarmDeliveryInputError('Engine facts batch must not be a symlink')
            document = engine.read(f'facts/{path.name}')
            if document is None:
                raise AlarmDeliveryInputError('Engine facts batch disappeared while reading')
            _, position = _facts(document, source_key=self.source_key)
            if path.name != f'{document["batch_id"]}.json':
                raise AlarmDeliveryInputError('Engine facts filename does not match batch identity')
            if _position_order(position) <= _position_order(producer_position) and (
                consumer is None or _position_order(position) > _position_order(consumer[1])
            ):
                pending.append((position, document))
        pending.sort(key=lambda pair: _position_order(pair[0]))
        if not pending or pending[-1][0] != producer_position:
            raise AlarmDeliveryInputError('Engine export cursor refers to an incomplete batch set')
        if any(
            _position_order(a[0]) == _position_order(b[0])
            for a, b in zip(pending, pending[1:], strict=False)
        ):
            raise AlarmDeliveryInputError('Multiple facts batches share a journal position')
        expected_previous = (
            None
            if consumer is None
            else {
                'batch_id': consumer[0]['batch_id'],
                'sha256': consumer[0]['batch_sha256'],
            }
        )
        for _, document in pending:
            if document['previous_batch'] != expected_previous:
                raise AlarmDeliveryInputError(
                    'Engine facts chain contains a missing or reordered batch'
                )
            expected_previous = {
                'batch_id': document['batch_id'],
                'sha256': document['sha256'],
            }
        if expected_previous != {
            'batch_id': producer_cursor['batch_id'],
            'sha256': producer_cursor['batch_sha256'],
        }:
            raise AlarmDeliveryInputError('Engine facts chain tip does not match export cursor')
        staged_count = 0
        last = None
        for position, document in pending[: self.max_facts_per_iteration]:
            pin = _reference(document['artifact_ref'])
            self._exact(pin)
            name = f'facts/{document["batch_id"]}.json'
            staged = inbox.read(name)
            if staged is not None and staged != document:
                raise AlarmDeliveryInputError('Previously received facts batch is inconsistent')
            context.assert_lease_current()
            with context.fenced_mutation():
                if staged is None:
                    inbox.replace(name, document)
                inbox.replace(
                    _CONSUMER_CURSOR_PATH,
                    {
                        'document_type': _CONSUMER_CURSOR_TYPE,
                        'schema_version': 2,
                        'artifact_ref': document['artifact_ref'],
                        'batch_id': document['batch_id'],
                        'batch_sha256': document['sha256'],
                        'journal_position': position.as_document(),
                    },
                )
            staged_count += 1
            last = document['batch_id']
        return staged_count, last

    def _fact_files(self) -> tuple[Path, ...]:
        path = self.engine_root / 'facts'
        if not path.exists():
            return ()
        return tuple(sorted(path.glob('facts-*.json')))
