from __future__ import annotations

import pytest

from ada.web.application.integrated_operations.modules.dashboard.ids import dashboard_card_content_id
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import TRANSPORTE
from ada.web.application.integrated_operations.modules.dashboard.mine.transporte import runtime
from ada.web.application.integrated_operations.modules.dashboard.mine.transporte.decoder import (
    decode_transporte_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.transporte.numero_operativo_turno import (
    NUMERO_OPERATIVO_TURNO_KPI_KEY,
    map_numero_operativo_turno_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.transporte.transporte_global_turno import (
    TRANSPORTE_GLOBAL_TURNO_KPI_KEY,
    map_transporte_global_turno_readings,
)
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.ui.display_status import DisplayStatus, DisplayValue

_KEYS = (TRANSPORTE_GLOBAL_TURNO_KPI_KEY, NUMERO_OPERATIVO_TURNO_KPI_KEY)


def _entry(value: object) -> dict[str, object]:
    return {'status': 'ok', 'value_kind': 'json', 'value': value,
            'value_type': None, 'parsed_value': None}


def _error() -> dict[str, object]:
    return {'status': 'error', 'value_kind': 'json', 'value': None,
            'value_type': None, 'parsed_value': None}


@pytest.mark.parametrize(('store', 'expected'), [
    (None, DisplayStatus.INVALID),
    ({}, DisplayStatus.NOT_MAPPED),
    ({'latest': None}, DisplayStatus.NOT_MAPPED),
    ({'latest': {'values': []}}, DisplayStatus.INVALID),
    ({'latest': {'values': {}}}, DisplayStatus.NOT_MAPPED),
])
def test_degraded_sources_are_independent(store, expected):
    values = decode_transporte_store(store)
    assert tuple(values) == _KEYS
    for mapper in (map_transporte_global_turno_readings, map_numero_operativo_turno_readings):
        state, status = mapper(values)
        assert state is None
        assert status is expected


def test_each_json_is_decoded_once_and_payload_is_reused():
    global_payload = {'data_state': 'unshift', 'rows': []}
    numero_payload = {'data_state': 'unshift', 'values': {}}
    prepared = decode_transporte_store({'latest': {'values': {
        _KEYS[0]: _entry(global_payload),
        _KEYS[1]: _entry(numero_payload),
    }}})
    assert prepared[_KEYS[0]].value is global_payload
    assert prepared[_KEYS[1]].value is numero_payload
    assert map_transporte_global_turno_readings(prepared)[1] is DisplayStatus.OK
    assert map_numero_operativo_turno_readings(prepared)[1] is DisplayStatus.OK


def test_one_invalid_kpi_does_not_affect_the_other():
    prepared = decode_transporte_store({'latest': {'values': {
        _KEYS[0]: {'status': 'ok', 'value_kind': 'value',
                   'value': '123', 'parsed_value': '123', 'value_type': 'text'},
        _KEYS[1]: _entry({'data_state': 'unshift', 'values': {}}),
    }}})
    assert map_transporte_global_turno_readings(prepared)[1] is DisplayStatus.INVALID
    assert map_numero_operativo_turno_readings(prepared)[1] is DisplayStatus.OK


def test_error_is_invalid_like_the_previous_mappers():
    prepared = decode_transporte_store({'latest': {'values': {key: _error() for key in _KEYS}}})
    assert all(value.status is DisplayStatus.INVALID for value in prepared.values())


def test_decoder_reads_component_and_each_requested_kpi_once(monkeypatch):
    from ada.web.application.integrated_operations.modules.dashboard.mine.transporte import decoder

    looked_up = []
    sources = []

    class Readings:
        def json(self, key):
            looked_up.append(key)
            return DisplayValue.not_mapped()

    def read(source):
        sources.append(source)
        return Readings()

    monkeypatch.setattr(decoder, 'read_component_latest', read)
    raw = object()
    assert tuple(decoder.decode_transporte_store(raw)) == _KEYS
    assert sources == [raw]
    assert looked_up == list(_KEYS)


class DashStub:
    def __init__(self):
        self.outputs = None
        self.render = None

    def callback(self, *arguments):
        self.outputs = arguments

        def register(fn):
            self.render = fn
            return fn

        return register


def test_runtime_shares_one_decoder_result_between_both_mappers(monkeypatch):
    prepared = decode_transporte_store({'latest': {'values': {}}})
    calls = []
    seen = []

    def decode(source):
        calls.append(source)
        return prepared

    def record(readings):
        seen.append(readings)
        return None, DisplayStatus.NOT_MAPPED

    monkeypatch.setattr(runtime, 'decode_transporte_store', decode)
    monkeypatch.setattr(runtime, 'map_transporte_global_turno_readings', record)
    monkeypatch.setattr(runtime, 'map_numero_operativo_turno_readings', record)
    monkeypatch.setattr(runtime, 'build_transporte', lambda **parts: parts)
    dash = DashStub()
    runtime.register_transporte_callback(dash, tool_key='operations')
    assert [output.component_id for output in dash.outputs[:2]] == [
        dashboard_card_content_id('transporte_global'),
        dashboard_card_content_id('numero_operativo'),
    ]
    assert dash.outputs[2].component_id == component_kpi_store_id(
        'operations', TRANSPORTE.tool_component_key
    )
    raw = {'latest': {'values': {}}}
    returned = dash.render(raw)
    assert tuple(returned) == ('transporte_global_turno', 'numero_operativo_turno')
    assert calls == [raw]
    assert seen == [prepared, prepared]
    assert seen[0] is seen[1]
