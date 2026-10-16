from copy import deepcopy

import pytest

from ada.web.alarms.collector.collector import AdaAlarmCollector
from ada.web.alarms.collector.contracts import AlarmLiveContractError
from ada.web.alarms.collector.models import (
    AlarmCollectorAvailability,
    AlarmCollectorRefreshStatus,
    AlarmLiveReadError,
)
from ada.web.alarms.collector.presentation import (
    project_alarm_live_store,
    resolve_alarm_live_browser_update,
)
from dash import no_update

from .test_contract import live


class Reader:
    def __init__(self):
        self.value = None
        self.calls = []
        self.error = None

    def read(self, *, tool_key):
        self.calls.append(tool_key)
        if self.error is not None:
            raise self.error
        return deepcopy(self.value)


def test_first_read_and_unchanged_use_single_tool_cache() -> None:
    reader = Reader()
    collector = AdaAlarmCollector(tool_key='tool-a', reader=reader)
    reader.value = live(count=1)
    assert collector.refresh().status is AlarmCollectorRefreshStatus.UPDATED
    snapshot = collector.snapshot
    assert snapshot.availability is AlarmCollectorAvailability.READY
    snapshot.document['alarms'].clear()
    assert len(collector.snapshot.document['alarms']) == 1
    assert collector.refresh().status is AlarmCollectorRefreshStatus.UNCHANGED
    assert reader.calls == ['tool-a', 'tool-a']


def test_missing_and_unavailable_preserve_last_good_document() -> None:
    reader = Reader()
    collector = AdaAlarmCollector(tool_key='tool-a', reader=reader)
    reader.value = live(count=1)
    collector.refresh()
    good = collector.snapshot.document
    reader.value = None
    assert collector.refresh().status is AlarmCollectorRefreshStatus.MISSING
    assert collector.snapshot.availability is AlarmCollectorAvailability.MISSING
    assert collector.snapshot.document == good
    reader.error = AlarmLiveReadError('Could not read Alarm Live from Cosmos')
    with pytest.raises(AlarmLiveReadError):
        collector.refresh()
    assert collector.snapshot.availability is AlarmCollectorAvailability.UNAVAILABLE
    assert collector.snapshot.document == good


def test_invalid_new_document_is_not_committed() -> None:
    reader = Reader()
    collector = AdaAlarmCollector(tool_key='tool-a', reader=reader)
    reader.value = live(count=1)
    collector.refresh()
    good = collector.snapshot.document
    reader.value['tool_key'] = 'foreign'
    with pytest.raises(AlarmLiveContractError):
        collector.refresh()
    assert collector.snapshot.availability is AlarmCollectorAvailability.INVALID
    assert collector.snapshot.document == good


def test_retirement_replaces_active_snapshot() -> None:
    reader = Reader()
    collector = AdaAlarmCollector(tool_key='tool-a', reader=reader)
    reader.value = live(count=1)
    collector.refresh()
    reader.value = live()
    reader.value['retired'] = True
    reader.value['semantic_sha256'] = 'c' * 64
    collector.refresh()
    assert collector.snapshot.availability is AlarmCollectorAvailability.RETIRED
    assert collector.snapshot.document['alarms'] == {}


def test_browser_store_updates_without_cosmos_and_keeps_last_good() -> None:
    reader = Reader()
    collector = AdaAlarmCollector(tool_key='tool-a', reader=reader)
    assert resolve_alarm_live_browser_update(collector.snapshot, browser_data={}) is no_update
    reader.value = live(count=1)
    collector.refresh()
    current = project_alarm_live_store(collector.snapshot)
    assert resolve_alarm_live_browser_update(collector.snapshot, browser_data=current) is no_update
    reader.value = None
    collector.refresh()
    updated = resolve_alarm_live_browser_update(collector.snapshot, browser_data=current)
    assert updated['availability'] == 'missing'
    assert updated['live'] == current['live']
    assert reader.calls == ['tool-a', 'tool-a']


def test_empty_initial_projection_recovers_when_cosmos_starts_delivering() -> None:
    reader = Reader()
    collector = AdaAlarmCollector(tool_key='tool-a', reader=reader)

    assert collector.refresh().status is AlarmCollectorRefreshStatus.MISSING
    empty = project_alarm_live_store(collector.snapshot)
    assert empty['availability'] == 'missing'
    assert empty['live'] is None

    reader.error = AlarmLiveReadError('Could not read Alarm Live from Cosmos')
    with pytest.raises(AlarmLiveReadError):
        collector.refresh()
    assert collector.snapshot.availability is AlarmCollectorAvailability.UNAVAILABLE
    assert collector.snapshot.document is None

    reader.error = None
    reader.value = live(count=1)
    assert collector.refresh().status is AlarmCollectorRefreshStatus.UPDATED
    assert collector.snapshot.availability is AlarmCollectorAvailability.READY
    assert len(collector.snapshot.document['alarms']) == 1


def test_recovery_after_missing_source_keeps_valid_cache_until_new_delivery() -> None:
    reader = Reader()
    collector = AdaAlarmCollector(tool_key='tool-a', reader=reader)
    reader.value = live(count=1)
    collector.refresh()
    original = collector.snapshot.document

    reader.error = AlarmLiveReadError('Could not read Alarm Live from Cosmos')
    with pytest.raises(AlarmLiveReadError):
        collector.refresh()
    assert collector.snapshot.document == original

    reader.error = None
    reader.value = live(count=1)
    assert collector.refresh().status is AlarmCollectorRefreshStatus.UNCHANGED
    assert collector.snapshot.availability is AlarmCollectorAvailability.READY
    assert collector.snapshot.document == original



def test_valid_live_with_zero_alarms_is_empty_not_missing() -> None:
    reader = Reader()
    reader.value = live(count=0)
    collector = AdaAlarmCollector(tool_key='tool-a', reader=reader)
    collector.refresh()
    assert collector.snapshot.availability is AlarmCollectorAvailability.EMPTY
    assert collector.snapshot.document is not None
    assert collector.snapshot.document['alarms'] == {}


def test_absent_container_keeps_previous_document_and_diagnostic() -> None:
    from ada.web.alarms.collector.models import AlarmLiveContainerMissingError

    reader = Reader()
    reader.value = live(count=1)
    collector = AdaAlarmCollector(tool_key='tool-a', reader=reader)
    collector.refresh()
    original = collector.snapshot.document
    reader.error = AlarmLiveContainerMissingError('container missing')
    with pytest.raises(AlarmLiveContainerMissingError):
        collector.refresh()
    assert collector.snapshot.availability is AlarmCollectorAvailability.CONTAINER_MISSING
    assert collector.snapshot.document == original
