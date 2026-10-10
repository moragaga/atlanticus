from __future__ import annotations

import pytest

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import MOLIENDA
from ada.web.application.integrated_operations.modules.dashboard.plant.molienda import runtime
from ada.web.application.integrated_operations.modules.dashboard.plant.molienda.decoder import (
    _KEYS,
    decode_molienda_store,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.molienda.overview import (
    map_molienda_overview_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.molienda.sags import (
    map_molienda_sags_readings,
)
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.ui.display_status import DisplayStatus, DisplayValue


def _entry(value: object, *, parsed: object = None):
    return {
        'status': 'ok',
        'value_kind': 'value',
        'value_type': 'text',
        'value': value,
        'parsed_value': value if parsed is None else parsed,
    }


def test_one_reading_per_distinct_kpi_and_no_implicit_keys(monkeypatch):
    assert len(_KEYS) == len(set(_KEYS)) == 62
    import ada.web.application.integrated_operations.modules.dashboard.plant.molienda.decoder as decoder

    original = decoder.decode_kpi_latest_value
    called = []

    def tracked(value, *, present):
        called.append((value, present))
        return original(value, present=present)

    monkeypatch.setattr(decoder, 'decode_kpi_latest_value', tracked)
    readings, timeseries = decoder.decode_molienda_store(
        {'latest': {'values': {_KEYS[0]: _entry('raw', parsed=' 1.234,5 ')}}}
    )
    assert len(called) == len(_KEYS)
    assert readings[_KEYS[0]] == DisplayValue.ok('1.234,5')
    assert timeseries is None
    assert all(key in readings for key in _KEYS)


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        (None, DisplayStatus.INVALID),
        ({}, DisplayStatus.NOT_MAPPED),
        ({'latest': None}, DisplayStatus.NOT_MAPPED),
        ({'latest': {'values': []}}, DisplayStatus.INVALID),
        ({'latest': {'values': {}}}, DisplayStatus.NOT_MAPPED),
    ],
)
def test_both_mappers_preserve_shared_source_status(source, expected):
    readings, timeseries = decode_molienda_store(source)
    overview = map_molienda_overview_readings(readings, timeseries)
    lines = map_molienda_sags_readings(readings)
    assert overview.trend_current.status is expected
    assert all(metric.value.status is expected for metric in overview.general)
    assert all(line.sag.state.status is expected for line in lines)
    assert all(line.sag.power.status is expected for line in lines)


def test_invalid_latest_does_not_hide_good_historical_series():
    timeseries = {'end_utc': 'bad', 'series': {}}
    readings, raw_timeseries = decode_molienda_store(
        {'latest': {'values': []}, 'timeseries': timeseries}
    )
    overview = map_molienda_overview_readings(readings, raw_timeseries)
    assert raw_timeseries is timeseries
    assert overview.trend_current.status is DisplayStatus.INVALID
    assert overview.trend_history.status is DisplayStatus.NOT_MAPPED


def test_degraded_entries_do_not_degrade_other_metrics():
    good, missing, error = _KEYS[:3]
    readings, timeseries = decode_molienda_store(
        {
            'latest': {
                'values': {
                    good: _entry('123'),
                    missing: {'status': 'missing', 'value_kind': None, 'value': None, 'value_type': None, 'parsed_value': None},
                    error: {'status': 'error', 'value_kind': 'value', 'value': None, 'value_type': 'text', 'parsed_value': None},
                }
            }
        }
    )
    assert readings[good].status is DisplayStatus.OK
    assert readings[missing].status is DisplayStatus.EMPTY
    assert readings[error].status is DisplayStatus.ERROR
    assert timeseries is None


class DashStub:
    def __init__(self):
        self.outputs = None
        self.render = None

    def callback(self, *args):
        self.outputs = args

        def register(fn):
            self.render = fn
            return fn

        return register


def test_callback_prepares_once_and_supplies_same_mapping_to_both_mappers(monkeypatch):
    source = {'latest': {'values': {}}}
    prepared = decode_molienda_store(source)
    calls = []
    received = []

    def decode(raw):
        calls.append(raw)
        return prepared

    def overview(values, history):
        received.append((values, history))
        return 'overview'

    def sags(values):
        received.append((values, None))
        return 'sags'

    monkeypatch.setattr(runtime, 'decode_molienda_store', decode)
    monkeypatch.setattr(runtime, 'map_molienda_overview_readings', overview)
    monkeypatch.setattr(runtime, 'map_molienda_sags_readings', sags)
    monkeypatch.setattr(runtime, 'build_molienda', lambda *parts: parts)
    app = DashStub()
    runtime.register_molienda_callback(app, tool_key='integrated_operations')
    assert len(app.outputs) == 2
    assert app.outputs[0].component_id == dashboard_card_content_id('molienda')
    assert app.outputs[1].component_id == component_kpi_store_id(
        'integrated_operations', MOLIENDA.tool_component_key
    )
    assert app.render(source) == ('overview', 'sags')
    assert calls == [source]
    assert len(received) == 2
    assert received[0][0] is prepared[0] and received[1][0] is prepared[0]
    assert received[0][1] is prepared[1]
