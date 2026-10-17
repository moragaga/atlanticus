from __future__ import annotations

import logging

from dash import no_update

from ada.web.alarms.collector.collector import AdaAlarmCollector
from ada.web.alarms.collector.integration import (
    ADA_ALARM_COLLECTOR_SERVICE_KEY,
    create_ada_alarm_collector_web_integration,
)
from ada.web.alarms.collector.presentation import AlarmCollectorPresentationSettings
from atlanticus.web.observability import WEB_OBSERVABILITY_SERVICE_KEY, WebObservability
from atlanticus.web.services import ServiceRegistry


class Reader:
    def read(self, *, tool_key):
        return None


class DashStub:
    def __init__(self):
        self.callbacks = []

    def callback(self, *_args, **kwargs):
        def register(fn):
            self.callbacks.append((fn, kwargs))
            return fn
        return register


def test_alarm_fast_retry_until_first_completed_read_then_normal():
    collector = AdaAlarmCollector(tool_key='tool-a', reader=Reader())
    integration = create_ada_alarm_collector_web_integration(
        collector, presentation_settings=AlarmCollectorPresentationSettings(),
    )
    services = ServiceRegistry()
    services.add(WEB_OBSERVABILITY_SERVICE_KEY, WebObservability(
        application='alarm-initial-test',
        logger=logging.getLogger('test.alarm.initial'), json_output=False,
    ))
    dash = DashStub()
    integration.module.register_services(services)
    integration.module.register_callbacks(dash, services)
    assert len(dash.callbacks) == 1
    refresh, kwargs = dash.callbacks[0]
    running = kwargs['running']
    assert len(running) == 1
    dependency, during, after = running[0]
    assert dependency.component_id == 'ada-alarm-collector-refresh'
    assert dependency.component_property == 'disabled'
    assert (during, after) == (True, False)

    waiting = {'tool_key': 'tool-a', 'availability': 'waiting', 'live': None}
    assert refresh(0, waiting, 1000) == (no_update, no_update)
    collector.refresh()
    missing, interval = refresh(1, waiting, 1000)
    assert missing['availability'] == 'missing'
    assert interval == 5000
    assert refresh(2, missing, 5000) == (no_update, no_update)


def test_alarm_ready_snapshot_switches_to_normal_interval_without_extra_callback():
    from copy import deepcopy

    from .test_contract import live

    class ReadyReader:
        def read(self, *, tool_key):
            return deepcopy(live(tool_key, count=1))

    collector = AdaAlarmCollector(tool_key='tool-a', reader=ReadyReader())
    services = ServiceRegistry()
    services.add(ADA_ALARM_COLLECTOR_SERVICE_KEY, collector)
    dash = DashStub()
    create_ada_alarm_collector_web_integration(collector).module.register_callbacks(
        dash, services,
    )
    refresh, _kwargs = dash.callbacks[0]
    waiting = {'tool_key': 'tool-a', 'availability': 'waiting', 'live': None}
    assert refresh(0, waiting, 1000) == (no_update, no_update)
    collector.refresh()
    ready, interval = refresh(1, waiting, 1000)
    assert ready['availability'] == 'ready'
    assert interval == 5000
    assert refresh(2, ready, 5000) == (no_update, no_update)


def test_alarm_unavailable_snapshot_ends_fast_retry():
    import pytest

    from ada.web.alarms.collector.models import AlarmLiveReadError

    class UnavailableReader:
        def read(self, *, tool_key):
            raise AlarmLiveReadError('Alarm source unavailable')

    collector = AdaAlarmCollector(tool_key='tool-a', reader=UnavailableReader())
    services = ServiceRegistry()
    services.add(ADA_ALARM_COLLECTOR_SERVICE_KEY, collector)
    dash = DashStub()
    create_ada_alarm_collector_web_integration(collector).module.register_callbacks(
        dash, services,
    )
    refresh, _kwargs = dash.callbacks[0]
    with pytest.raises(AlarmLiveReadError):
        collector.refresh()
    store, interval = refresh(1, {'tool_key': 'tool-a', 'availability': 'waiting'}, 1000)
    assert store['availability'] == 'unavailable'
    assert interval == 5000


def test_alarm_normal_refresh_interval_can_be_configured():
    collector = AdaAlarmCollector(tool_key='tool-a', reader=Reader())
    services = ServiceRegistry()
    services.add(ADA_ALARM_COLLECTOR_SERVICE_KEY, collector)
    dash = DashStub()
    create_ada_alarm_collector_web_integration(
        collector,
        presentation_settings=AlarmCollectorPresentationSettings(refresh_interval_seconds=6),
    ).module.register_callbacks(dash, services)
    refresh, _kwargs = dash.callbacks[0]
    collector.refresh()
    _, interval = refresh(1, {'tool_key': 'tool-a', 'availability': 'waiting'}, 1000)
    assert interval == 6000
