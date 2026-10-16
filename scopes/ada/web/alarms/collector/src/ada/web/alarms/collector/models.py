from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class AlarmLiveReadError(RuntimeError):
    pass


class AlarmLiveContainerMissingError(AlarmLiveReadError):
    pass


class AlarmCollectorAvailability(StrEnum):
    WAITING = 'waiting'
    READY = 'ready'
    EMPTY = 'empty'
    CONTAINER_MISSING = 'container_missing'
    RETIRED = 'retired'
    MISSING = 'missing'
    INVALID = 'invalid'
    UNAVAILABLE = 'unavailable'


class AlarmCollectorRefreshStatus(StrEnum):
    UPDATED = 'updated'
    UNCHANGED = 'unchanged'
    MISSING = 'missing'


@dataclass(frozen=True, slots=True)
class AlarmCollectorSnapshot:
    tool_key: str
    availability: AlarmCollectorAvailability
    semantic_sha256: str | None
    document: dict | None


@dataclass(frozen=True, slots=True)
class AlarmCollectorRefreshResult:
    status: AlarmCollectorRefreshStatus
    semantic_sha256: str | None = None


class AlarmDeliveryReader(Protocol):
    def read(self, *, tool_key: str) -> dict | None: ...
