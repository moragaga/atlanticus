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
)
from atlanticus.state import AtomicJsonStore

_CURRENT_TYPE = 'ada_command_center_engine_resolved_current_state'
_CURRENT_PATH = 'current/latest.json'
_HASH = re.compile(r'[0-9a-f]{64}\Z')


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


@dataclass(frozen=True, slots=True)
class DeliveryInputCycleResult:
    current_status: str


@dataclass(slots=True)
class LocalAlarmDeliveryReceiver:
    volume_path: Path
    source_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.volume_path, Path) or not self.volume_path.is_absolute():
            raise ValueError('VOLUMEN_PATH must be an absolute Path')
        if (
            not isinstance(self.source_key, str)
            or not self.source_key
            or self.source_key != self.source_key.strip()
        ):
            raise ValueError('ALARM_CONFIGURATION_SOURCE_KEY must be non-empty text')

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
        current = AtomicJsonStore(root_path=self.inbox_root, max_document_bytes=None).read(
            _CURRENT_PATH
        )
        if current is not None:
            _current(current, source_key=self.source_key)

    def consume(self, context: object) -> DeliveryInputCycleResult:
        context.assert_lease_current()
        inbox = AtomicJsonStore(root_path=self.inbox_root, max_document_bytes=None)
        engine = AtomicJsonStore(root_path=self.engine_root, max_document_bytes=None)
        return DeliveryInputCycleResult(
            current_status=self._stage_current(context, inbox, engine),
        )

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
