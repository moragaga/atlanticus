from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from atlanticus.state import AtomicJsonStore

SCHEMA_VERSION = 1


class AlarmRotationError(ValueError):
    pass


def _digest(value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        .encode('utf-8')
    ).hexdigest()


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise AlarmRotationError('Rotation clock must be UTC')
    return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith('Z'):
        raise AlarmRotationError('Rotation deadline must be a UTC timestamp')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise AlarmRotationError('Rotation deadline is invalid') from error
    if result.utcoffset() != timedelta(0):
        raise AlarmRotationError('Rotation deadline must be UTC')
    return result


def _rotation_state(value: object) -> dict:
    if isinstance(value, dict) and set(value) == {'normal', 'areas'}:
        if not isinstance(value['normal'], dict) or set(value['normal']) != {'queue', 'visible', 'next_due_at'}:
            raise AlarmRotationError('Distributed normal rotation state is invalid')
        _rotation_state(value['normal'])
        areas = value['areas']
        if not isinstance(areas, dict) or set(areas) - {'MINE', 'PLANT'}:
            raise AlarmRotationError('Distributed area states are invalid')
        for area_state in areas.values():
            if not isinstance(area_state, dict) or set(area_state) != {'queue', 'visible', 'next_due_at'}:
                raise AlarmRotationError('Distributed area rotation state is invalid')
            _rotation_state(area_state)
        return value
    if not isinstance(value, dict) or set(value) != {'queue', 'visible', 'next_due_at'}:
        raise AlarmRotationError('Rotation state has invalid fields')
    queue, visible = value['queue'], value['visible']
    if (
        not isinstance(queue, list)
        or not isinstance(visible, list)
        or any(not isinstance(x, str) or not x for x in (*queue, *visible))
        or len(queue) != len(set(queue))
        or len(visible) != len(set(visible))
        or not set(visible).issubset(queue)
    ):
        raise AlarmRotationError('Rotation state contains invalid occurrences')
    if value['next_due_at'] is not None:
        _parse_timestamp(value['next_due_at'])
    return value


def _visible_from_tool(tool: Mapping[str, object] | None) -> list[str]:
    if tool is None:
        return []
    result = []
    for item in tool['operator_view']:
        if 'group' in item:
            return []
        result.append(item['occurrence_id'])
    return result


def is_grouped(tool: Mapping[str, object] | None) -> bool:
    return bool(tool is not None and any('group' in item for item in tool['operator_view']))


def plan_rotation(
    *,
    tool: Mapping[str, object],
    previous_tool: Mapping[str, object] | None,
    state: dict | None,
    now: datetime,
    rotation_seconds: float,
) -> tuple[dict, dict, datetime | None]:
    _timestamp(now)
    if (
        isinstance(rotation_seconds, bool)
        or not isinstance(rotation_seconds, int | float)
        or not math.isfinite(rotation_seconds)
        or rotation_seconds <= 0
    ):
        raise AlarmRotationError('Rotation interval must be positive')
    if is_grouped(tool):
        raise AlarmRotationError('Distributed rotation requires a separate policy')
    pool = tool['operator_pool']
    slots = tool['meta']['max_visible_slots']
    if not isinstance(pool, list) or len(set(pool)) != len(pool) or slots < 1:
        raise AlarmRotationError('Rotation pool or slot count is invalid')
    if state is not None:
        _rotation_state(state)
        queue = [item for item in state['queue'] if item in pool]
        previous_visible = [item for item in state['visible'] if item in pool]
        due = None if state['next_due_at'] is None else _parse_timestamp(state['next_due_at'])
    else:
        previous_visible = [item for item in _visible_from_tool(previous_tool) if item in pool]
        queue = [item for item in pool if item not in previous_visible] + previous_visible
        due = None
    queue += [item for item in pool if item not in queue]
    if len(pool) <= slots:
        visible = list(pool)
        queue = list(pool)
        due = None
    elif not previous_visible:
        visible = queue[:slots]
        queue = queue[slots:] + visible
        due = now + timedelta(seconds=rotation_seconds)
    elif due is None:
        visible = previous_visible[:slots]
        visible += [item for item in queue if item not in visible][:slots - len(visible)]
        queue = [item for item in queue if item not in visible] + visible
        due = now + timedelta(seconds=rotation_seconds)
    elif now >= due:
        visible = queue[:slots]
        queue = queue[slots:] + visible
        due = now + timedelta(seconds=rotation_seconds)
    else:
        visible = previous_visible[:slots]
        visible += [item for item in queue if item not in visible][:slots - len(visible)]
        queue = [item for item in queue if item not in visible] + visible
    updated = dict(tool)
    updated['operator_view'] = [
        {'slot': index, 'occurrence_id': item} for index, item in enumerate(visible, start=1)
    ]
    updated['meta'] = {**tool['meta'], 'operator_count': len(visible),
                       'rotation_pending': len(pool) > slots}
    result = {'queue': queue, 'visible': visible,
              'next_due_at': None if due is None else _timestamp(due)}
    return updated, result, due


@dataclass(slots=True)
class ToolRotationMemory:
    root: Path

    def __post_init__(self) -> None:
        if not isinstance(self.root, Path) or not self.root.is_absolute():
            raise AlarmRotationError('Rotation memory root must be absolute')

    @staticmethod
    def _seal(document: dict) -> dict:
        return {**document, 'sha256': _digest(document)}

    def _store(self) -> AtomicJsonStore:
        return AtomicJsonStore(root_path=self.root, max_document_bytes=None)

    @staticmethod
    def _path(tool_key: str) -> str:
        if not isinstance(tool_key, str) or not tool_key or tool_key != tool_key.strip():
            raise AlarmRotationError('Rotation Tool identity is invalid')
        return f'state/rotation/{hashlib.sha256(tool_key.encode("utf-8")).hexdigest()}.json'

    def read(self, *, tool_key: str, previous_tool: dict | None) -> dict | None:
        document = self._store().read(self._path(tool_key))
        if document is None:
            return None
        if (
            not isinstance(document, dict)
            or set(document) != {'schema_version', 'tool_key', 'committed', 'prepared', 'sha256'}
            or document['schema_version'] != SCHEMA_VERSION
            or document['tool_key'] != tool_key
            or document['sha256'] != _digest({k: v for k, v in document.items() if k != 'sha256'})
        ):
            raise AlarmRotationError('Rotation memory document is invalid')
        fingerprint = None if previous_tool is None else _digest(previous_tool)
        for key in ('prepared', 'committed'):
            candidate = document[key]
            if candidate is None:
                continue
            if not isinstance(candidate, dict) or set(candidate) != {'tool_sha256', 'state'}:
                raise AlarmRotationError('Rotation memory record is invalid')
            if not isinstance(candidate['tool_sha256'], str):
                raise AlarmRotationError('Rotation memory fingerprint is invalid')
            _rotation_state(candidate['state'])
            if fingerprint == candidate['tool_sha256']:
                return candidate['state']
        if previous_tool is None and document['committed'] is None:
            return None
        raise AlarmRotationError('Rotation memory disagrees with the published Tool')

    def prepare(
        self, *, tool_key: str, previous_tool: dict | None,
        old_state: dict | None, next_tool: dict, next_state: dict,
    ) -> None:
        _rotation_state(next_state)
        path = self._path(tool_key)
        document = {
            'schema_version': SCHEMA_VERSION,
            'tool_key': tool_key,
            'committed': (
                None if previous_tool is None or old_state is None else
                {'tool_sha256': _digest(previous_tool), 'state': old_state}
            ),
            'prepared': {'tool_sha256': _digest(next_tool), 'state': next_state},
        }
        self._store().replace(path, self._seal(document))

    def confirm(self, *, tool_key: str, current_tool: dict) -> None:
        path = self._path(tool_key)
        document = self._store().read(path)
        if document is None or document['tool_key'] != tool_key:
            raise AlarmRotationError('Rotation memory confirmation has no preparation')
        if document['sha256'] != _digest({k: v for k, v in document.items() if k != 'sha256'}):
            raise AlarmRotationError('Rotation memory checksum mismatch')
        prepared = document['prepared']
        if prepared is None or prepared['tool_sha256'] != _digest(current_tool):
            raise AlarmRotationError('Rotation memory confirmation differs from publication')
        self._store().replace(path, self._seal({
            'schema_version': SCHEMA_VERSION, 'tool_key': tool_key,
            'committed': prepared, 'prepared': None,
        }))
