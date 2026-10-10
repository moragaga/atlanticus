from __future__ import annotations

import pytest

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import FLOTACION
from ada.web.application.integrated_operations.modules.dashboard.plant.flotacion import runtime
from ada.web.application.integrated_operations.modules.dashboard.plant.flotacion.colectiva.overview import (
    map_colectiva_overview_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.flotacion.colectiva.process import (
    map_colectiva_process_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.flotacion.decoder import (
    _KEYS,
    decode_flotacion_store,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.flotacion.selectiva.espesadores import (
    map_espesadores_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.flotacion.selectiva.indicators import (
    map_selectiva_indicators_readings,
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


def test_keys_are_complete_unique_and_decoded_once(monkeypatch):
    assert len(_KEYS) == len(set(_KEYS)) == 67
    import ada.web.application.integrated_operations.modules.dashboard.plant.flotacion.decoder as decoder

    original = decoder.decode_kpi_latest_value
    called = []

    def tracked(value, *, present):
        called.append((value, present))
        return original(value, present=present)

    monkeypatch.setattr(decoder, 'decode_kpi_latest_value', tracked)
    readings, timeseries = decoder.decode_flotacion_store(
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
def test_shared_source_status_reaches_both_cards(source, expected):
    readings, timeseries = decode_flotacion_store(source)
    overview = map_colectiva_overview_readings(readings, timeseries)
    process = map_colectiva_process_readings(readings)
    tanks = map_espesadores_readings(readings)
    indicators = map_selectiva_indicators_readings(readings)
    assert overview.trend_current.status is expected
    assert all(item.value.status is expected for item in overview.indicators)
    assert all(item.state.status is expected for item in process.roughers)
    assert all(item.feed.status is expected for item in tanks)
    assert all(item.value.status is expected for item in indicators)
    if source is None:
        assert overview.trend_history.status is DisplayStatus.INVALID


def test_raw_timeseries_is_shared_unchanged_even_when_latest_is_invalid():
    timeseries = {'end_utc': 'bad', 'series': {}}
    readings, raw_timeseries = decode_flotacion_store(
        {'latest': {'values': []}, 'timeseries': timeseries}
    )
    overview = map_colectiva_overview_readings(readings, raw_timeseries)
    assert raw_timeseries is timeseries
    assert overview.trend_current.status is DisplayStatus.INVALID
    assert overview.trend_history.status is DisplayStatus.NOT_MAPPED


def test_degraded_entries_do_not_affect_other_keys():
    good, missing, error = _KEYS[:3]
    readings, _ = decode_flotacion_store({
        'latest': {'values': {
            good: _entry('OK'),
            missing: {'status': 'missing', 'value_kind': None, 'value': None,
                      'value_type': None, 'parsed_value': None},
            error: {'status': 'error', 'value_kind': 'value', 'value': None,
                    'value_type': 'text', 'parsed_value': None},
        }}
    })
    assert readings[good].status is DisplayStatus.OK
    assert readings[missing].status is DisplayStatus.EMPTY
    assert readings[error].status is DisplayStatus.ERROR


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


def test_one_callback_decodes_once_and_delivers_same_readings_to_four_mappers(monkeypatch):
    source = {'latest': {'values': {}}}
    prepared = decode_flotacion_store(source)
    calls = []
    received = []

    def decode(raw):
        calls.append(raw)
        return prepared

    def mapper(label):
        def map_readings(values, *args):
            received.append((label, values, args))
            return label
        return map_readings

    monkeypatch.setattr(runtime, 'decode_flotacion_store', decode)
    monkeypatch.setattr(runtime, 'map_colectiva_overview_readings', mapper('overview'))
    monkeypatch.setattr(runtime, 'map_colectiva_process_readings', mapper('process'))
    monkeypatch.setattr(runtime, 'map_espesadores_readings', mapper('espesadores'))
    monkeypatch.setattr(runtime, 'map_selectiva_indicators_readings', mapper('indicators'))
    monkeypatch.setattr(runtime, 'build_flotacion', lambda *parts: parts[:2])
    app = DashStub()
    runtime.register_flotacion_callback(app, tool_key='integrated_operations')
    assert len(app.outputs) == 3
    assert app.outputs[0].component_id == dashboard_card_content_id('colectiva')
    assert app.outputs[1].component_id == dashboard_card_content_id('selectiva')
    assert app.outputs[2].component_id == component_kpi_store_id(
        'integrated_operations', FLOTACION.tool_component_key
    )
    assert app.render(source) == ('overview', 'process')
    assert calls == [source]
    assert len(received) == 4
    assert all(value is prepared[0] for _, value, _ in received)
    assert received[0][2] == (prepared[1],)
    assert all(args == () for _, _, args in received[1:])
