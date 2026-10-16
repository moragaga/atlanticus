from __future__ import annotations

import logging

from dash import no_update

from ada.web.alarms.collector.collector import AdaAlarmCollector
from ada.web.alarms.collector.integration import create_ada_alarm_collector_web_integration
from ada.web.alarms.collector.presentation import AlarmCollectorPresentationSettings
from atlanticus.web.observability import WEB_OBSERVABILITY_SERVICE_KEY, WebObservability
from atlanticus.web.services import ServiceRegistry


class Reader:
    def read(self, *, tool_key):
        return None


class DashStub:
    def __init__(self):
        self.callbacks = []

    def callback(self, *_args):
        def register(fn):
            self.callbacks.append(fn)
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
    adapt, refresh = dash.callbacks
    waiting = {'tool_key': 'tool-a', 'availability': 'waiting', 'live': None}
    assert adapt(waiting, 1000) is no_update
    assert adapt(waiting, 1000) is no_update
    collector.refresh()
    missing = refresh(1, waiting)
    assert missing['availability'] == 'missing'
    assert adapt(missing, 1000) == 5000
