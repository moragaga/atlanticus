from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import PUERTO
from ada.web.application.integrated_operations.modules.dashboard.plant.puerto import (
    decoder,
    runtime,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.puerto.decoder import (
    _KEYS,
    _LEVEL_KEYS,
    decode_puerto_store,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.puerto.desaladora import (
    FLUJO_TREND,
    VOLUMEN,
    map_desaladora_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.puerto.puerto import (
    FILTERS,
    FILTRADO_ACCUMULATED,
    FILTRADO_TREND,
    SHIPMENT,
    TANKS,
    map_puerto_readings,
)
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.ui.display_status import DisplayStatus, DisplayValue

_END = datetime(2026, 4, 5, 4, tzinfo=UTC)
_START = _END - timedelta(hours=1)


def _entry(value, *, parsed=None):
    return {
        'status': 'ok',
        'value_kind': 'value',
        'value_type': 'text',
        'value': str(value),
        'parsed_value': str(value) if parsed is None else parsed,
    }


def _history(value):
    return {
        'hours': 1,
        'start_utc': _START.isoformat(),
        'end_utc': _END.isoformat(),
        'value_type': 'float',
        'values': [None, 0.0, value] + [None] * 27,
    }


def _store():
    values = {key: _entry('12.5') for key in _KEYS}
    values[SHIPMENT.duration_key] = _entry(3600)
    values[SHIPMENT.state_key] = _entry('Operando')
    for tank in TANKS:
        values[tank.level_key] = _entry(55)
        values[tank.color_key] = _entry(2)
    for definition in FILTERS:
        values[definition.state_key] = _entry('Operando')
    return {
        'latest': {'values': values},
        'timeseries': {
            'step_seconds': 120,
            'end_utc': _END.isoformat(),
            'series': {
                FILTRADO_TREND.kpi_key: _history(15.4),
                FLUJO_TREND.kpi_key: _history(6.1),
            },
        },
    }


def test_contracts_from_both_legacy_sources():
    assert FILTRADO_TREND.kpi_key == 'filtrado_real_mean_hora'
    assert FILTRADO_ACCUMULATED.kpi_key == 'filtrado_acumulado_dia'
    assert [tank.label for tank in TANKS] == ['TK-60', 'TK-61', 'TK-62', 'TK-63']
    assert [tank.level_key for tank in TANKS] == [f'nivel_tk_0{n}_inst' for n in ('60', '61', '62', '63')]
    assert [definition.label for definition in FILTERS] == [
        'FL-001', 'FL-002', 'FL-003', 'FL-004', 'FL-005', 'FL-006', 'FL-702', 'FL-703'
    ]
    assert SHIPMENT.tonnage.kpi_key == 'embarque_tonelaje_actual_inst'
    assert SHIPMENT.duration_key == 'embarque_tiempo_actual_inst'
    assert SHIPMENT.state_key == 'embarque_estado_inst'
    assert FLUJO_TREND.kpi_key == 'flujo_real_mean_hora'
    assert VOLUMEN.kpi_key == 'volumen_real_acc_dia'
    assert len(_KEYS) == len(set(_KEYS)) == 23
    assert len(_LEVEL_KEYS) == 4


def test_latest_is_decoded_once_per_distinct_key(monkeypatch):
    calls = []
    original = decoder.decode_kpi_latest_value

    def tracked(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(decoder, 'decode_kpi_latest_value', tracked)
    data = _store()
    readings, histories = decode_puerto_store(data)
    assert len(calls) == len(_KEYS) - len(_LEVEL_KEYS)
    assert len(readings) == 23
    assert readings[FILTRADO_TREND.kpi_key].value == '12.5'
    assert readings[TANKS[0].level_key].value == '55'
    assert len(histories) == 2


def test_charts_are_independent_and_preserve_complete_120_second_series():
    data = _store()
    readings, histories = decode_puerto_store(data)
    puerto = map_puerto_readings(readings, histories)
    desaladora = map_desaladora_readings(readings, histories)
    assert puerto.trend_history.status is DisplayStatus.OK
    assert desaladora.trend_history.status is DisplayStatus.OK
    assert len(puerto.trend_history.points) == len(desaladora.trend_history.points) == 30
    assert puerto.trend_history.points[-1].timestamp_utc == _END
    assert [item.value for item in puerto.trend_history.points[:3]] == [None, 0.0, 15.4]
    assert [item.value for item in desaladora.trend_history.points[:3]] == [None, 0.0, 6.1]
    data['timeseries']['series'][FLUJO_TREND.kpi_key]['values'][2] = 'bad'
    readings, histories = decode_puerto_store(data)
    assert histories[FILTRADO_TREND.kpi_key].status is DisplayStatus.OK
    assert histories[FLUJO_TREND.kpi_key].status is DisplayStatus.INVALID
    assert readings[FLUJO_TREND.kpi_key].status is DisplayStatus.OK


@pytest.mark.parametrize(
    ('store', 'status'),
    [
        (None, DisplayStatus.INVALID),
        ({}, DisplayStatus.NOT_MAPPED),
        ({'latest': {'values': None}}, DisplayStatus.INVALID),
        ({'latest': {'values': {}}}, DisplayStatus.NOT_MAPPED),
    ],
)
def test_both_cards_keep_degraded_statuses(store, status):
    readings, histories = decode_puerto_store(store)
    puerto = map_puerto_readings(readings, histories)
    desaladora = map_desaladora_readings(readings, histories)
    assert puerto.trend_current.status is status
    assert puerto.accumulated.status is status
    assert desaladora.trend_current.status is status
    assert desaladora.volume.status is status
    assert all(item.state.status is status for item in puerto.filters)


def test_invalid_individual_state_is_not_assumed_operational():
    data = _store()
    data['latest']['values'][FILTERS[0].state_key] = _entry('Unknown')
    data['latest']['values'][SHIPMENT.state_key] = {
        'status': 'error', 'value_kind': 'json', 'value': None,
        'value_type': None, 'parsed_value': None,
    }
    readings, histories = decode_puerto_store(data)
    puerto = map_puerto_readings(readings, histories)
    assert puerto.filters[0].state.status is DisplayStatus.INVALID
    assert puerto.filters[1].state.value == 'operando'
    assert puerto.ship_state.status is DisplayStatus.ERROR
    data['latest']['values'][SHIPMENT.state_key]['value_kind'] = None
    malformed, histories = decode_puerto_store(data)
    assert map_puerto_readings(malformed, histories).ship_state.status is DisplayStatus.INVALID
    assert all(tank.state_override == 'operando' for tank in puerto.tanks)
    assert puerto.tanks[0].tone == 'warning'


@pytest.mark.parametrize(('seconds', 'display', 'unit'), [
    (0, '0', ''), (59, '59', 's'), (60, '1', 'm'),
    (3599, '59', 'm'), (3600, '>1', 'h'), (86400, '>1', 'd'),
])
def test_shipment_duration_legacy_boundaries(seconds, display, unit):
    data = _store()
    data['latest']['values'][SHIPMENT.duration_key] = _entry(seconds)
    readings, histories = decode_puerto_store(data)
    puerto = map_puerto_readings(readings, histories)
    assert puerto.duration == DisplayValue.ok(display)
    assert puerto.duration_unit == unit


class DashStub:
    def __init__(self):
        self.args = None
        self.callback_fn = None

    def callback(self, *args):
        self.args = args

        def register(fn):
            self.callback_fn = fn
            return fn

        return register


def test_one_callback_has_two_outputs_and_one_input(monkeypatch):
    store = _store()
    prepared = decode_puerto_store(store)
    calls = []
    refs = []

    def decode(source):
        calls.append(source)
        return prepared

    def port(readings, histories):
        refs.append((readings, histories))
        return 'Puerto'

    def desal(readings, histories):
        refs.append((readings, histories))
        return 'Desaladora'

    monkeypatch.setattr(runtime, 'decode_puerto_store', decode)
    monkeypatch.setattr(runtime, 'map_puerto_readings', port)
    monkeypatch.setattr(runtime, 'map_desaladora_readings', desal)
    monkeypatch.setattr(runtime, 'build_puerto_component', lambda *args: args)
    app = DashStub()
    runtime.register_puerto_callback(app, tool_key='integrated_operations')
    assert len(app.args) == 3
    assert app.args[0].component_id == dashboard_card_content_id('puerto')
    assert app.args[1].component_id == dashboard_card_content_id('desaladora')
    assert app.args[2].component_id == component_kpi_store_id('integrated_operations', PUERTO.tool_component_key)
    assert app.callback_fn(store) == ('Puerto', 'Desaladora')
    assert calls == [store]
    assert len(refs) == 2
    assert refs[0][0] is refs[1][0] is prepared[0]
    assert refs[0][1] is refs[1][1] is prepared[1]
