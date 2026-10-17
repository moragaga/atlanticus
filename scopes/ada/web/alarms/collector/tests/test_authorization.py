from __future__ import annotations

from copy import deepcopy

from dash import html, no_update

from ada.web.alarms.collector.collector import AdaAlarmCollector
from ada.web.alarms.collector.integration import create_ada_alarm_collector_web_integration
from ada.web.alarms.collector.presentation import alarm_live_store_id

from .test_contract import live


class Reader:
    def read(self, *, tool_key):
        return deepcopy(live(tool_key))


class DashStub:
    def __init__(self):
        self.render = None

    def callback(self, *_args, **_kwargs):
        def decorate(function):
            self.render = function
            return function
        return decorate


class ServiceStub:
    def __init__(self, collector):
        self.collector = collector

    def require(self, _name, _type):
        return self.collector


def test_denied_session_cannot_receive_initial_or_refreshed_alarm_payload():
    allowed = False
    collector = AdaAlarmCollector(tool_key='tool-a', reader=Reader())
    collector.refresh()
    integration = create_ada_alarm_collector_web_integration(
        collector, can_view=lambda: allowed,
    )
    root = integration.wrap_layout(lambda: html.Div(children=[]))()
    interval, store = root.children
    assert store.id == alarm_live_store_id('tool-a')
    assert store.data['live'] is None
    assert store.data['semantic_sha256'] is None
    dash = DashStub()
    integration.module.register_callbacks(dash, ServiceStub(collector))
    exposed = {'tool_key': 'tool-a', 'live': {'private': 'stale'}}
    denied, interval_update = dash.render(1, exposed, 1000)
    assert denied['live'] is None
    assert denied['semantic_sha256'] is None
    assert denied['tool_key'] == 'tool-a'
    assert interval_update == 5000
    assert dash.render(2, denied, 5000) == (no_update, no_update)
    allowed = True
    granted, unchanged_interval = dash.render(3, denied, 5000)
    assert granted['live'] is not None
    assert unchanged_interval is no_update
    allowed = False
    revoked, unchanged_interval = dash.render(4, granted, 5000)
    assert revoked['live'] is None
    assert unchanged_interval is no_update
