from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType

from .errors import TimeStatusStoreContractError

_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


class TimeStatusTimestampQuality(StrEnum):
    VALID = 'valid'
    MISSING = 'missing'
    INVALID = 'invalid'


@dataclass(frozen=True, slots=True)
class TimeStatusSourceTimestamp:
    key: str
    quality: TimeStatusTimestampQuality
    timestamp_utc: datetime | None = None

    def __post_init__(self) -> None:
        _require_key(self.key, field_name='source key')
        if self.quality is TimeStatusTimestampQuality.VALID:
            if self.timestamp_utc is None:
                raise TimeStatusStoreContractError('VALID source timestamp requires timestamp_utc')
            if self.timestamp_utc.tzinfo is None or self.timestamp_utc.utcoffset() is None:
                raise TimeStatusStoreContractError('timestamp_utc must be timezone-aware')
            object.__setattr__(self, 'timestamp_utc', self.timestamp_utc.astimezone(UTC))
            return
        if self.timestamp_utc is not None:
            raise TimeStatusStoreContractError(
                f'{self.quality.value.upper()} source timestamp cannot expose timestamp_utc'
            )

    @property
    def timestamp_iso(self) -> str | None:
        if self.timestamp_utc is None:
            return None
        return self.timestamp_utc.isoformat().replace('+00:00', 'Z')


@dataclass(frozen=True, slots=True)
class TimeStatusStoreSnapshot:
    tool_key: str
    generated_at_utc: datetime
    sources: Mapping[str, TimeStatusSourceTimestamp]

    def __post_init__(self) -> None:
        _require_key(self.tool_key, field_name='tool key')
        if self.generated_at_utc.tzinfo is None or self.generated_at_utc.utcoffset() is None:
            raise TimeStatusStoreContractError('generated_at_utc must be timezone-aware')
        object.__setattr__(self, 'generated_at_utc', self.generated_at_utc.astimezone(UTC))

        normalized: dict[str, TimeStatusSourceTimestamp] = {}
        for key, source in self.sources.items():
            _require_key(key, field_name='source key')
            if source.key != key:
                raise TimeStatusStoreContractError('Source mapping key must match source.key')
            normalized[key] = source
        object.__setattr__(self, 'sources', MappingProxyType(normalized))

    @property
    def generated_at_iso(self) -> str:
        return self.generated_at_utc.isoformat().replace('+00:00', 'Z')

    def source(self, key: str) -> TimeStatusSourceTimestamp:
        _require_key(key, field_name='source key')
        source = self.sources.get(key)
        if source is not None:
            return source
        return TimeStatusSourceTimestamp(
            key=key,
            quality=TimeStatusTimestampQuality.MISSING,
        )


def _require_key(value: str, *, field_name: str) -> None:
    if not _KEY_PATTERN.fullmatch(value):
        raise TimeStatusStoreContractError(f'Invalid Time Status {field_name}: {value!r}')
