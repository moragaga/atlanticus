from __future__ import annotations

import pytest

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import (
    TRANSPORTE_FLUIDOS,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos import (
    decoder,
    runtime,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.decoder import (
    _KEYS,
    _SCALAR_KEYS,
    decode_transporte_fluidos_store,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.sta import (
    STA_INDICATORS,
    map_sta_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.stc import (
    STC_LEVELS,
    map_stc_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.str.overview import (
    STR_TREND,
    map_str_overview_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.tranque import (
    TRANQUE_INDICATORS,
    map_tranque_readings,
)
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.ui.display_status import DisplayStatus


def _entry(value, *, parsed=None):
    return {
        'status': 'ok', 'value_kind': 'value', 'value_type': 'text',
        'value': str(value), 'parsed_value': str(value if parsed is None else parsed),
    }


def test_one_decode_per_unique_kpi(monkeypatch):
    assert len(_KEYS) == len(set(_KEYS)) == 55
    assert _SCALAR_KEYS == {definition.level_key for definition in STC_LEVELS}
    called = []
    original = decoder.read_component_latest

    def tracked(store):
        source = original(store)
        class Tracked:
            def text(self, key):
                called.append(('text', key))
                return source.text(key)
            def scalar(self, key):
                called.append(('scalar', key))
                return source.scalar(key)
        return Tracked()

    monkeypatch.setattr(decoder, 'read_component_latest', tracked)
    readings = decode_transporte_fluidos_store({'latest': {'values': {}}})
    assert len(readings) == 55
    assert len(called) == 55
    assert len({key for _, key in called}) == 55
    assert {key for kind, key in called if kind == 'scalar'} == _SCALAR_KEYS


def test_text_and_scalar_readings_retain_distinct_contracts():
    key = STC_LEVELS[0].level_key
    text = STA_INDICATORS[0].kpi_key
    raw = {
        'latest': {'values': {
            key: _entry('42', parsed='99'),
            text: _entry(' raw ', parsed=' parsed '),
        }}
    }
    readings = decode_transporte_fluidos_store(raw)
    assert readings[key].value == '42'
    assert readings[text].value == ' parsed '
    assert map_stc_readings(readings).levels[0].level.value == '42'
    assert map_sta_readings(readings)[0].value.value == ' parsed '


@pytest.mark.parametrize(('store', 'status'), [
    (None, DisplayStatus.INVALID),
    ({}, DisplayStatus.NOT_MAPPED),
    ({'latest': {'values': []}}, DisplayStatus.INVALID),
    ({'latest': {'values': {}}}, DisplayStatus.NOT_MAPPED),
])
def test_degraded_latest_status_remains_independent_from_timeseries(store, status):
    readings = decode_transporte_fluidos_store(store)
    assert readings[STR_TREND.kpi_key].status is status
    assert map_str_overview_readings(readings, store).history.status is (
        DisplayStatus.INVALID if store is None else DisplayStatus.NOT_MAPPED
    )


def test_one_card_does_not_degrade_other_card():
    a, b = STA_INDICATORS[0].kpi_key, TRANQUE_INDICATORS[0].kpi_key
    readings = decode_transporte_fluidos_store({'latest': {'values': {
        a: _entry('17'),
        b: {'status': 'error', 'value_kind': 'json', 'value_type': None, 'value': None, 'parsed_value': None},
    }}})
    assert map_sta_readings(readings)[0].value.status is DisplayStatus.OK
    assert map_tranque_readings(readings)[0].value.status is DisplayStatus.ERROR


class DashStub:
    def __init__(self):
        self.args = None
        self.render = None
    def callback(self, *args):
        self.args = args
        def register(fn):
            self.render = fn
            return fn
        return register


def test_one_callback_fans_out_same_readings_and_keeps_raw_history(monkeypatch):
    raw = {'latest': {'values': {}}}
    prepared = decode_transporte_fluidos_store(raw)
    decoding = []
    received = []

    def decode(source):
        decoding.append(source)
        return prepared

    def mapper(name):
        def inner(values, *rest):
            received.append((name, values, rest))
            return name
        return inner

    monkeypatch.setattr(runtime, 'decode_transporte_fluidos_store', decode)
    for attr in (
        'map_str_overview_readings', 'map_str_espesadores_readings',
        'map_str_ductos_readings', 'map_stc_readings',
        'map_tranque_readings', 'map_sta_readings',
    ):
        monkeypatch.setattr(runtime, attr, mapper(attr))
    monkeypatch.setattr(runtime, 'build_transporte_fluidos', lambda *sections: sections[:4])
    app = DashStub()
    runtime.register_transporte_fluidos_callback(app, tool_key='operations')
    assert len(app.args) == 5
    assert [item.component_id for item in app.args[:4]] == [
        dashboard_card_content_id(name) for name in ('str', 'stc', 'tranque', 'sta')
    ]
    assert app.args[4].component_id == component_kpi_store_id(
        'operations', TRANSPORTE_FLUIDOS.tool_component_key
    )
    assert len(app.render(raw)) == 4
    assert len(received) == 6
    assert decoding == [raw]
    assert all(item[1] is prepared for item in received)
    assert received[0][2] == (raw,)
    assert all(item[2] == () for item in received[1:])
