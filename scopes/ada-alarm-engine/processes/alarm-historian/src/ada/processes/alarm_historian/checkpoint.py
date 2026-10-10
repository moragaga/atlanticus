from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ada.contracts.alarms.facts_stream import FactsStreamPosition
from atlanticus.state import AtomicJsonStore

_CHECKPOINT_PATH = 'state/historian-checkpoint.json'
_DOCUMENT_TYPE = 'ada_alarm_historian_checkpoint'
_SCHEMA_VERSION = 1
_SEGMENT = re.compile(r'facts/year=\d{4}/month=\d{2}/day=\d{2}/hour=\d{2}/part-\d{4}\.jsonl')
_DIGEST = re.compile(r'[0-9a-f]{64}')


class AlarmHistorianCheckpointError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AlarmHistorianCheckpoint:
    stream_id: str
    producer_application: str
    position: FactsStreamPosition


class AlarmHistorianCheckpointStore:
    def __init__(
        self,
        *,
        root: Path,
        stream_id: str,
        producer_application: str,
    ) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError('Checkpoint root must be an absolute Path')
        self._stream_id = _identity(stream_id, 'stream_id')
        self._producer_application = _identity(producer_application, 'producer_application')
        self._store = AtomicJsonStore(root_path=root)

    def read(self) -> AlarmHistorianCheckpoint | None:
        document = self._store.read(_CHECKPOINT_PATH)
        if document is None:
            return None
        if not isinstance(document, dict) or set(document) != {
            'document_type', 'schema_version', 'stream_id', 'producer_application',
            'position', 'sha256',
        }:
            raise AlarmHistorianCheckpointError('Historian checkpoint shape is invalid')
        if (
            document['document_type'] != _DOCUMENT_TYPE
            or type(document['schema_version']) is not int
            or document['schema_version'] != _SCHEMA_VERSION
            or not isinstance(document['sha256'], str)
            or _DIGEST.fullmatch(document['sha256']) is None
            or document['sha256'] != _digest({k: v for k, v in document.items() if k != 'sha256'})
        ):
            raise AlarmHistorianCheckpointError('Historian checkpoint integrity is invalid')
        if (
            document['stream_id'] != self._stream_id
            or document['producer_application'] != self._producer_application
        ):
            raise AlarmHistorianCheckpointError('Historian checkpoint source identity has changed')
        return AlarmHistorianCheckpoint(
            stream_id=self._stream_id,
            producer_application=self._producer_application,
            position=_decode_position(document['position']),
        )

    def save(self, position: FactsStreamPosition) -> AlarmHistorianCheckpoint:
        encoded = _encode_position(position)
        previous = self.read()
        if previous is not None:
            old = previous.position
            old_key = (old.segment_path, old.record_end)
            new_key = (position.segment_path, position.record_end)
            if new_key < old_key:
                raise AlarmHistorianCheckpointError('Historian checkpoint cannot move backwards')
            if new_key == old_key:
                if _encode_position(old) != encoded:
                    raise AlarmHistorianCheckpointError('Historian checkpoint position has changed')
                return previous
        document = {
            'document_type': _DOCUMENT_TYPE,
            'schema_version': _SCHEMA_VERSION,
            'stream_id': self._stream_id,
            'producer_application': self._producer_application,
            'position': encoded,
        }
        self._store.replace(_CHECKPOINT_PATH, {**document, 'sha256': _digest(document)})
        return AlarmHistorianCheckpoint(self._stream_id, self._producer_application, position)


def _identity(value: str, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f'{name} must be non-empty normalized text')
    return value


def _digest(document: dict) -> str:
    return hashlib.sha256(
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        .encode('utf-8')
    ).hexdigest()


def _encode_position(position: FactsStreamPosition) -> dict:
    if not isinstance(position, FactsStreamPosition):
        raise TypeError('position must be a FactsStreamPosition')
    if not isinstance(position.segment_path, str) or _SEGMENT.fullmatch(position.segment_path) is None:
        raise AlarmHistorianCheckpointError('Historian checkpoint segment is invalid')
    if (
        not isinstance(position.record_start, int)
        or isinstance(position.record_start, bool)
        or not isinstance(position.record_end, int)
        or isinstance(position.record_end, bool)
        or position.record_start < 0
        or position.record_end <= position.record_start
    ):
        raise AlarmHistorianCheckpointError('Historian checkpoint offsets are invalid')
    if not isinstance(position.record_sha256, str) or _DIGEST.fullmatch(position.record_sha256) is None:
        raise AlarmHistorianCheckpointError('Historian checkpoint record digest is invalid')
    if not isinstance(position.artifact_ref, dict):
        raise AlarmHistorianCheckpointError('Historian checkpoint artifact is invalid')
    return {
        'segment_path': position.segment_path,
        'record_start': position.record_start,
        'record_end': position.record_end,
        'record_sha256': position.record_sha256,
        'artifact_ref': position.artifact_ref,
    }


def _decode_position(value: object) -> FactsStreamPosition:
    if not isinstance(value, dict) or set(value) != {
        'segment_path', 'record_start', 'record_end', 'record_sha256', 'artifact_ref',
    }:
        raise AlarmHistorianCheckpointError('Historian checkpoint position shape is invalid')
    position = FactsStreamPosition(**value)
    _encode_position(position)
    return position
