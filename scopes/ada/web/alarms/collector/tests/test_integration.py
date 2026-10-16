from copy import deepcopy

from dash import html

from ada.web.alarms.collector.collector import AdaAlarmCollector
from ada.web.alarms.collector.integration import create_ada_alarm_collector_web_integration
from ada.web.alarms.collector.presentation import (
    AlarmCollectorPresentationSettings,
    DEFAULT_ALARM_BROWSER_INTERVAL_SECONDS,
    alarm_live_store_id,
)

from .test_contract import live


class Reader:
    def read(self, *, tool_key):
        return deepcopy(live(tool_key))


def test_integration_wraps_layout_without_polling_cosmos() -> None:
    collector = AdaAlarmCollector(tool_key='tool-a', reader=Reader())
    integration = create_ada_alarm_collector_web_integration(collector)
    root = html.Div(id='application', children=[])
    wrapped = integration.wrap_layout(lambda: root)
    assert wrapped() is root
    interval, store = root.children
    assert interval.id == 'ada-alarm-collector-refresh'
    assert store.id == alarm_live_store_id('tool-a')
    assert store.data['availability'] == 'waiting'
    assert integration.module.name == 'ada-alarm-collector'


def test_browser_interval_defaults_to_five_seconds_but_is_independent() -> None:
    assert DEFAULT_ALARM_BROWSER_INTERVAL_SECONDS == 5.0
    settings = AlarmCollectorPresentationSettings()
    collector = AdaAlarmCollector(tool_key='tool-a', reader=Reader())
    integration = create_ada_alarm_collector_web_integration(
        collector, presentation_settings=settings,
    )
    layout = integration.wrap_layout(lambda: html.Div(children=[]))()
    interval = layout.children[0]
    assert interval.interval == 1000

    custom = create_ada_alarm_collector_web_integration(
        collector,
        presentation_settings=AlarmCollectorPresentationSettings(refresh_interval_seconds=6),
    )
    custom_layout = custom.wrap_layout(lambda: html.Div(children=[]))()
    assert custom_layout.children[0].interval == 1000
