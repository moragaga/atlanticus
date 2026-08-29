from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from .contracts import TimeStatusStoreDocumentSource
from .errors import TimeStatusStoreContractError, TimeStatusToolScopeError
from .models import (
    TimeStatusSourceTimestamp,
    TimeStatusStoreSnapshot,
    TimeStatusTimestampQuality,
    _require_key,
)


class TimeStatusStoreAdapter:
    def __init__(self, source: TimeStatusStoreDocumentSource) -> None:
        self._source = source

    def load_snapshot(self, *, tool_key: str) -> TimeStatusStoreSnapshot | None:
        _require_key(tool_key, field_name='tool key')
        document = self._source.load_time_status_document(tool_key=tool_key)
        if document is None:
            return None
        return parse_time_status_store_document(document, expected_tool_key=tool_key)


def parse_time_status_store_document(
    document: Mapping[str, object],
    *,
    expected_tool_key: str,
) -> TimeStatusStoreSnapshot:
    _require_key(expected_tool_key, field_name='tool key')
    actual_tool_key = document.get('tool_key')
    if not isinstance(actual_tool_key, str):
        raise TimeStatusStoreContractError('Time Status store document requires tool_key')
    _require_key(actual_tool_key, field_name='tool key')
    if actual_tool_key != expected_tool_key:
        raise TimeStatusToolScopeError(
            f'Time Status snapshot belongs to {actual_tool_key!r}, not {expected_tool_key!r}'
        )

    generated_at_utc = _parse_required_timestamp(
        document.get('generated_at_utc'),
        field_name='generated_at_utc',
    )
    raw_sources = document.get('sources')
    if not isinstance(raw_sources, Mapping):
        raise TimeStatusStoreContractError('Time Status store document requires sources mapping')

    sources: dict[str, TimeStatusSourceTimestamp] = {}
    for raw_key, raw_timestamp in raw_sources.items():
        if not isinstance(raw_key, str):
            raise TimeStatusStoreContractError('Time Status source keys must be strings')
        _require_key(raw_key, field_name='source key')
        sources[raw_key] = _parse_source_timestamp(raw_key, raw_timestamp)

    return TimeStatusStoreSnapshot(
        tool_key=actual_tool_key,
        generated_at_utc=generated_at_utc,
        sources=sources,
    )


def _parse_source_timestamp(key: str, value: object) -> TimeStatusSourceTimestamp:
    if value is None:
        return TimeStatusSourceTimestamp(
            key=key,
            quality=TimeStatusTimestampQuality.MISSING,
        )
    timestamp = _try_parse_timestamp(value)
    if timestamp is None:
        return TimeStatusSourceTimestamp(
            key=key,
            quality=TimeStatusTimestampQuality.INVALID,
        )
    return TimeStatusSourceTimestamp(
        key=key,
        quality=TimeStatusTimestampQuality.VALID,
        timestamp_utc=timestamp,
    )


def _parse_required_timestamp(value: object, *, field_name: str) -> datetime:
    timestamp = _try_parse_timestamp(value)
    if timestamp is None:
        raise TimeStatusStoreContractError(
            f'Time Status store {field_name} must be a timezone-aware ISO-8601 timestamp'
        )
    return timestamp


def _try_parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith('Z'):
            normalized = f'{normalized[:-1]}+00:00'
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)
