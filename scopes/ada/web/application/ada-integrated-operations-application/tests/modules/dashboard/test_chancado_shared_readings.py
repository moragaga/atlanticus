from __future__ import annotations

import pytest

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import CHANCADO_STMG
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg import (
    runtime,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.correas_stmg import (
    CORREAS_STMG_DEFINITIONS,
    CORREAS_STMG_METRIC,
    map_correas_stmg_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.decoder import (
    decode_chancado_stmg_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.equipos_ch import (
    EQUIPOS_CH_DEFINITIONS,
    map_equipos_ch_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.feeders import (
    FEEDERS_CH_DEFINITIONS,
    map_feeders_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.leyes import (
    LEYES_DEFINITIONS,
    map_leyes_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.produccion_global import (
    PRODUCCION_GLOBAL_DEFINITIONS,
    map_produccion_global_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.stockpile import (
    STOCKPILE_MINA_KPI_KEYS,
    map_stockpile_mina_readings,
)
from ada.web.kpis.collector import component_kpi_store_id
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
    prepared = decode_chancado_stmg_store(source)
    return (
        map_produccion_global_readings(prepared),
        map_equipos_ch_readings(prepared, EQUIPOS_CH_DEFINITIONS),
        map_stockpile_mina_readings(prepared),
        map_feeders_readings(prepared, FEEDERS_CH_DEFINITIONS),
        map_correas_stmg_readings(prepared, CORREAS_STMG_DEFINITIONS, CORREAS_STMG_METRIC),
        map_leyes_readings(prepared),
    )


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        (None, DisplayStatus.INVALID),
        ({}, DisplayStatus.NOT_MAPPED),
        ({'latest': {'values': []}}, DisplayStatus.INVALID),
        (_store({}), DisplayStatus.NOT_MAPPED),
        (_store({'unused': _value('123')}), DisplayStatus.NOT_MAPPED),
    ],
)
def test_all_six_mappers_keep_source_status(source, expected):
    production, equipment, stockpiles, feeders, belts, laws = _map_all(source)
    assert production.rows[0].real.value.status is expected
    assert equipment[0].state.status is expected
    assert stockpiles[0].percent.status is expected
    assert feeders[0].percent.status is expected
    assert belts.states[0].status is expected
    assert laws.rows[0].hora.value.status is expected


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
    prepared = decode_chancado_stmg_store(source)
    assert map_produccion_global_readings(prepared).rows[0].real.value.value == '1.234,5'
    assert map_leyes_readings(prepared).rows[0].hora.value.value == ' 8,42 '
    assert map_feeders_readings(prepared, FEEDERS_CH_DEFINITIONS)[0].percent.value == 87
    assert map_stockpile_mina_readings(prepared)[0].percent.value == '65,0'


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
    result = map_produccion_global_readings(decode_chancado_stmg_store(source)).rows[0]
    assert result.real.value.status is DisplayStatus.ERROR
    assert result.plan_acumulado.value.status is DisplayStatus.EMPTY
    assert result.proyeccion.value.status is DisplayStatus.INVALID
    assert result.plan_dia.value.status is DisplayStatus.INVALID
    assert result.requerido_hora.value.status is DisplayStatus.NOT_MAPPED


class DashStub:
    def __init__(self) -> None:
        self.render = None
        self.dependencies = None

    def callback(self, *args):
        self.dependencies = args
        def register(function):
            self.render = function
            return function

        return register


def test_callback_shares_same_preparation_between_all_six_mappers(monkeypatch):
    received = []
    for name in (
        'map_produccion_global_readings',
        'map_equipos_ch_readings',
        'map_stockpile_mina_readings',
        'map_feeders_readings',
        'map_correas_stmg_readings',
        'map_leyes_readings',
    ):
        def record(source, *_args):
            received.append(source)
            return None

        monkeypatch.setattr(runtime, name, record)

    calls = []
    original = runtime.decode_chancado_stmg_store

    def tracked(source):
        calls.append(source)
        return original(source)

    monkeypatch.setattr(runtime, 'decode_chancado_stmg_store', tracked)
    monkeypatch.setattr(runtime, 'build_chancado_stmg', lambda **states: states)
    dash = DashStub()
    runtime.register_chancado_stmg_callback(dash, tool_key='operations')
    assert len(dash.dependencies) == 2
    assert dash.dependencies[0].component_id == dashboard_card_content_id('chancado_stmg')
    assert dash.dependencies[0].component_property == 'children'
    assert dash.dependencies[1].component_id == component_kpi_store_id(
        'operations', CHANCADO_STMG.tool_component_key
    )
    assert dash.dependencies[1].component_property == 'data'
    store = _store({})
    assert len(dash.render(store)) == 6
    assert calls == [store]
    assert len(received) == 6
    assert all(readings is received[0] for readings in received)
    assert received[0] is not store


def test_decoder_reads_all_active_kpis_once_with_correct_representation(monkeypatch):
    from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg import (
        decoder,
    )
    from ada.web.ui.display_status import DisplayValue

    calls = []

    class ReadingsStub:
        def text(self, key):
            calls.append(('text', key))
            return DisplayValue.not_mapped()

        def scalar(self, key):
            calls.append(('scalar', key))
            return DisplayValue.not_mapped()

    source = {'latest': {'values': {}}}
    received = []

    def read(store):
        received.append(store)
        return ReadingsStub()

    monkeypatch.setattr(decoder, 'read_component_latest', read)
    prepared = decoder.decode_chancado_stmg_store(source)

    assert received == [source]
    assert len(calls) == len(set(calls))
    assert len(calls) == len(prepared)
    assert {key for _, key in calls} == set(prepared)
    assert ('scalar', FEEDERS_CH_DEFINITIONS[0].percent_kpi_key) in calls
    assert ('text', PRODUCCION_GLOBAL_DEFINITIONS[0].real_key) in calls
    assert ('text', STOCKPILE_MINA_KPI_KEYS[0][1]) in calls
