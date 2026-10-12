from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass

from dash import no_update

from ada.web.alarms.collector.contracts import required_key
from ada.web.alarms.collector.models import (
    AlarmCollectorAvailability,
    AlarmCollectorSnapshot,
)

ALARM_LIVE_STORE_TYPE = 'ada-alarm-live-store'
DEFAULT_ALARM_BROWSER_INTERVAL_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class AlarmCollectorPresentationSettings:
    refresh_interval_seconds: float = DEFAULT_ALARM_BROWSER_INTERVAL_SECONDS
    interval_id: str = 'ada-alarm-collector-refresh'

    def __post_init__(self) -> None:
        if (
            isinstance(self.refresh_interval_seconds, bool)
            or not isinstance(self.refresh_interval_seconds, int | float)
            or not math.isfinite(self.refresh_interval_seconds)
            or self.refresh_interval_seconds <= 0
        ):
            raise ValueError('Alarm browser interval must be positive and finite')
        required_key(self.interval_id, 'interval_id')


def alarm_live_store_id(tool_key: str) -> dict[str, str]:
    return {'type': ALARM_LIVE_STORE_TYPE, 'tool': required_key(tool_key, 'tool_key')}


def project_alarm_live_store(snapshot: AlarmCollectorSnapshot) -> dict:
    return {
        'tool_key': snapshot.tool_key,
        'availability': snapshot.availability.value,
        'semantic_sha256': snapshot.semantic_sha256,
        'live': deepcopy(snapshot.document),
    }


def resolve_alarm_live_browser_update(
    snapshot: AlarmCollectorSnapshot, *, browser_data: object,
) -> object:
    if not isinstance(snapshot, AlarmCollectorSnapshot):
        raise TypeError('Alarm collector snapshot is invalid')
    if snapshot.availability is AlarmCollectorAvailability.WAITING:
        return no_update
    candidate = project_alarm_live_store(snapshot)
    if not isinstance(browser_data, dict) or browser_data.get('tool_key') != snapshot.tool_key:
        return candidate
    if snapshot.document is None and browser_data.get('live') is not None:
        candidate['live'] = deepcopy(browser_data['live'])
        candidate['semantic_sha256'] = browser_data.get('semantic_sha256')
    if candidate == browser_data:
        return no_update
    return candidate
