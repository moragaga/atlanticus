from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from atlanticus.observability import EventProjection, EventSeverity, ObservabilityEvent
from atlanticus.observability.operational import OperationalEventProjection

_REMOTE_SEVERITIES = frozenset(
    {
        EventSeverity.WARNING,
        EventSeverity.ERROR,
        EventSeverity.CRITICAL,
    }
)


class AzureProblemEventProjection(EventProjection):
    def __init__(self) -> None:
        self._operational = OperationalEventProjection()

    def project(
        self,
        event: ObservabilityEvent,
        payload: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        if not isinstance(event, ObservabilityEvent):
            raise TypeError('event must be an ObservabilityEvent')
        if not isinstance(payload, Mapping):
            raise TypeError('payload must be a mapping')
        if event.severity not in _REMOTE_SEVERITIES:
            return None
        return self._operational.project(event, payload)
