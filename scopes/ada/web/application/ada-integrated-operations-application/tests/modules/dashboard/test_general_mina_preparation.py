from __future__ import annotations

import pytest

from ada.web.application.integrated_operations.modules.dashboard.mine.general_mina import (
    decoder,
    runtime,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.general_mina.mp10 import (
    MP10_HOTEL_MINA_INST_KPI_KEY,
    MP10_HOTEL_MINA_PROY_KPI_KEY,
    map_mp10_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.general_mina.remanentes import (
    STOCK_3080_KPI_KEY,
    map_remanentes_readings,
)
from ada.web.kpis.readings import KpiLatestReadings
from ada.web.ui.display_status import DisplayStatus


def _entry(value: object, *, kind: str = 'value', parsed: str | None = None):
    return {
        'status': 'ok',
        'value_kind': kind,
        'value_type': 'text' if kind == 'value' else None,
        'value': value,
        'parsed_value': parsed if kind == 'value' else None,
    }


def test_component_prepares_seven_distinct_kpis_once(monkeypatch):
    calls = []
    original_json = KpiLatestReadings.json
    original_text = KpiLatestReadings.text

    def traced_json(self, key):
        calls.append(key)
        return original_json(self, key)

    def traced_text(self, key):
        calls.append(key)
        return original_text(self, key)

    monkeypatch.setattr(KpiLatestReadings, 'json', traced_json)
    monkeypatch.setattr(KpiLatestReadings, 'text', traced_text)
    source = {
        'latest': {
            'values': {
                STOCK_3080_KPI_KEY: _entry('1234.5', parsed='1.234,5'),
                MP10_HOTEL_MINA_INST_KPI_KEY: _entry(
                    {'value': '25', 'alert': None, 'status': '0'}, kind='json'
                ),
            }
        }
    }
    values = decoder.decode_general_mina_store(source)
    assert len(values) == 7
    assert len(calls) == len(set(calls)) == 7
    assert values[STOCK_3080_KPI_KEY].value == '1.234,5'
    assert map_remanentes_readings(values).stock_3080.value.value == '1.234,5'
    assert map_mp10_readings(values).instant.value == '25'
    assert values[MP10_HOTEL_MINA_PROY_KPI_KEY].status is DisplayStatus.NOT_MAPPED


@pytest.mark.parametrize(
    ('source', 'status'),
    [
        (None, DisplayStatus.INVALID),
        ({'latest': None}, DisplayStatus.NOT_MAPPED),
        ({'latest': {'values': []}}, DisplayStatus.INVALID),
    ],
)
def test_all_cards_share_degraded_source_status(source, status):
    values = decoder.decode_general_mina_store(source)
    assert all(reading.status is status for reading in values.values())


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


def test_callback_has_one_input_and_four_independent_outputs():
    dash = DashStub()
    runtime.register_general_mina_callback(dash, tool_key='operations')
    assert len(dash.args) == 5
    assert [output.component_id for output in dash.args[:4]] == [
        'ada-integrated-operations-card-movimiento_mina-content',
        'ada-integrated-operations-card-remanentes-content',
        'ada-integrated-operations-card-perforacion-content',
        'ada-integrated-operations-card-mp10-content',
    ]
    assert len(dash.render({'latest': None})) == 4


def test_callback_prepares_once_and_shares_result_with_every_mapper(monkeypatch):
    received = []
    calls = []
    real_decoder = runtime.decode_general_mina_store

    def prepare(store_data):
        calls.append(store_data)
        return real_decoder(store_data)

    def record(source):
        received.append(source)
        return source

    monkeypatch.setattr(runtime, 'decode_general_mina_store', prepare)
    for name in (
        'map_movimiento_mina_readings',
        'map_remanentes_readings',
        'map_perforacion_readings',
        'map_mp10_readings',
    ):
        monkeypatch.setattr(runtime, name, record)
    monkeypatch.setattr(runtime, 'build_general_mina', lambda **states: states)
    dash = DashStub()
    runtime.register_general_mina_callback(dash, tool_key='operations')
    store = {'latest': None}
    result = dash.render(store)
    assert calls == [store]
    assert len(result) == 4
    assert len(received) == 4
    assert all(value is received[0] for value in received)
    assert received[0] is not store


def test_movimiento_source_error_remains_invalid_for_ui(monkeypatch):
    from ada.web.application.integrated_operations.modules.dashboard.mine.general_mina.movimiento_mina import (
        MOVIMIENTO_MINA_KPI_KEY,
    )

    captured = []
    monkeypatch.setattr(runtime, 'build_general_mina', lambda **states: captured.append(states) or states)
    dash = DashStub()
    runtime.register_general_mina_callback(dash, tool_key='operations')
    store = {
        'latest': {
            'values': {
                MOVIMIENTO_MINA_KPI_KEY: {
                    'status': 'error',
                    'value_kind': 'json',
                    'value_type': None,
                    'value': None,
                    'parsed_value': None,
                }
            }
        }
    }
    dash.render(store)
    assert captured[0]['movimiento_mina'] is DisplayStatus.INVALID
