from __future__ import annotations

import pytest

from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg import (
    runtime,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.correas_stmg import (
    CORREAS_STMG_DEFINITIONS,
    CORREAS_STMG_METRIC,
    map_correas_stmg_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.equipos_ch import (
    EQUIPOS_CH_DEFINITIONS,
    map_equipos_ch_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.feeders import (
    FEEDERS_CH_DEFINITIONS,
    map_feeders_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.leyes import (
    LEYES_DEFINITIONS,
    map_leyes_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.produccion_global import (
    PRODUCCION_GLOBAL_DEFINITIONS,
    map_produccion_global_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.stockpile import (
    STOCKPILE_MINA_KPI_KEYS,
    map_stockpile_mina_store,
)
from ada.web.kpis.readings import read_component_latest
from ada.web.ui.display_status import DisplayStatus


def _value(value: str, parsed: str | None = None) -> dict[str, object]:
    return {
        'status': 'ok',
        'value_kind': 'value',
        'value_type': 'text',
        'value': value,
        'parsed_value': value if parsed is None else parsed,
    }


def _store(values: dict[str, object]) -> dict[str, object]:
    return {'latest': {'values': values}}


def _map_all(source: object) -> tuple[object, ...]:
    return (
        map_produccion_global_store(source),
        map_equipos_ch_store(source, EQUIPOS_CH_DEFINITIONS),
        map_stockpile_mina_store(source),
        map_feeders_store(source, FEEDERS_CH_DEFINITIONS),
        map_correas_stmg_store(source, CORREAS_STMG_DEFINITIONS, CORREAS_STMG_METRIC),
        map_leyes_store(source),
    )


@pytest.mark.parametrize(
    'source',
    [
        None,
        {},
        {'latest': {'values': []}},
        _store({}),
        _store({'unused': _value('123')}),
    ],
)
def test_all_six_mappers_match_store_and_prepared_readings(source):
    assert _map_all(source) == _map_all(read_component_latest(source))


def test_scalar_representations_are_not_interchanged():
    production_key = PRODUCCION_GLOBAL_DEFINITIONS[0].real_key
    law_key = LEYES_DEFINITIONS[0].hora_key
    feeder_key = FEEDERS_CH_DEFINITIONS[0].percent_kpi_key
    pile_key = STOCKPILE_MINA_KPI_KEYS[0][1]
    source = _store(
        {
            production_key: _value('1234.5', ' 1.234,5 '),
            law_key: _value('8.42', ' 8,42 '),
            feeder_key: _value('87', '87,0'),
            pile_key: _value('65', '65,0'),
        }
    )
    prepared = read_component_latest(source)
    assert map_produccion_global_store(prepared).rows[0].real.value.value == '1.234,5'
    assert map_leyes_store(prepared).rows[0].hora.value.value == ' 8,42 '
    assert map_feeders_store(prepared, FEEDERS_CH_DEFINITIONS)[0].percent.value == 87
    assert map_stockpile_mina_store(prepared)[0].percent.value == '65,0'


def test_degraded_statuses_are_kept_independent():
    first = PRODUCCION_GLOBAL_DEFINITIONS[0]
    source = _store(
        {
            first.real_key: {
                'status': 'error',
                'value_kind': 'value',
                'value_type': 'text',
                'value': None,
                'parsed_value': None,
            },
            first.plan_acumulado_key: {
                'status': 'missing',
                'value_kind': None,
                'value_type': None,
                'value': None,
                'parsed_value': None,
            },
            first.proyeccion_key: {'status': 'not-a-valid-entry'},
            first.plan_dia_key: _value('  '),
        }
    )
    result = map_produccion_global_store(read_component_latest(source)).rows[0]
    assert result.real.value.status is DisplayStatus.ERROR
    assert result.plan_acumulado.value.status is DisplayStatus.EMPTY
    assert result.proyeccion.value.status is DisplayStatus.INVALID
    assert result.plan_dia.value.status is DisplayStatus.INVALID
    assert result.requerido_hora.value.status is DisplayStatus.NOT_MAPPED


class DashStub:
    def __init__(self) -> None:
        self.render = None

    def callback(self, *_args):
        def register(function):
            self.render = function
            return function

        return register


def test_callback_shares_same_readings_between_all_six_mappers(monkeypatch):
    received = []
    for name in (
        'map_produccion_global_store',
        'map_equipos_ch_store',
        'map_stockpile_mina_store',
        'map_feeders_store',
        'map_correas_stmg_store',
        'map_leyes_store',
    ):
        def record(source, *_args):
            received.append(source)
            return None

        monkeypatch.setattr(runtime, name, record)

    calls = []
    original = runtime.read_component_latest

    def tracked(source):
        calls.append(source)
        return original(source)

    monkeypatch.setattr(runtime, 'read_component_latest', tracked)
    monkeypatch.setattr(runtime, 'build_chancado_stmg', lambda **states: states)
    dash = DashStub()
    runtime.register_chancado_stmg_callback(dash, tool_key='operations')
    store = _store({})
    assert len(dash.render(store)) == 6
    assert calls == [store]
    assert len(received) == 6
    assert all(readings is received[0] for readings in received)
    assert received[0] is not store
