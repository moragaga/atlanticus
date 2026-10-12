from __future__ import annotations

from copy import deepcopy
from threading import RLock

from ada.web.alarms.collector.contracts import (
    AlarmLiveContractError,
    required_key,
    validate_live_document,
)
from ada.web.alarms.collector.models import (
    AlarmCollectorAvailability,
    AlarmCollectorRefreshResult,
    AlarmCollectorRefreshStatus,
    AlarmCollectorSnapshot,
    AlarmDeliveryReader,
    AlarmLiveReadError,
)


class AdaAlarmCollector:
    def __init__(self, *, tool_key: str, reader: AlarmDeliveryReader) -> None:
        self._tool_key = required_key(tool_key, 'tool_key')
        if not callable(getattr(reader, 'read', None)):
            raise TypeError('Alarm reader must provide read')
        self._reader = reader
        self._availability = AlarmCollectorAvailability.WAITING
        self._document: dict | None = None
        self._lock = RLock()

    @property
    def tool_key(self) -> str:
        return self._tool_key

    @property
    def snapshot(self) -> AlarmCollectorSnapshot:
        with self._lock:
            return AlarmCollectorSnapshot(
                tool_key=self._tool_key,
                availability=self._availability,
                semantic_sha256=(
                    None if self._document is None else self._document['semantic_sha256']
                ),
                document=deepcopy(self._document),
            )

    def refresh(self) -> AlarmCollectorRefreshResult:
        try:
            candidate = self._reader.read(tool_key=self._tool_key)
        except AlarmLiveReadError:
            self._mark(AlarmCollectorAvailability.UNAVAILABLE)
            raise
        if candidate is None:
            self._mark(AlarmCollectorAvailability.MISSING)
            return AlarmCollectorRefreshResult(AlarmCollectorRefreshStatus.MISSING)
        try:
            document = validate_live_document(candidate, tool_key=self._tool_key)
        except AlarmLiveContractError:
            self._mark(AlarmCollectorAvailability.INVALID)
            raise
        availability = (
            AlarmCollectorAvailability.RETIRED if document['retired']
            else AlarmCollectorAvailability.READY
        )
        with self._lock:
            if self._document is not None and (
                self._document['semantic_sha256'] == document['semantic_sha256']
            ):
                self._availability = availability
                return AlarmCollectorRefreshResult(
                    AlarmCollectorRefreshStatus.UNCHANGED, document['semantic_sha256']
                )
            self._document = document
            self._availability = availability
        return AlarmCollectorRefreshResult(
            AlarmCollectorRefreshStatus.UPDATED, document['semantic_sha256']
        )

    def _mark(self, availability: AlarmCollectorAvailability) -> None:
        with self._lock:
            self._availability = availability
