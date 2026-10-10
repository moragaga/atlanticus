from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import FLOTACION
from ada.web.application.integrated_operations.modules.dashboard.plant.flotacion.colectiva import (
    BOMBAS,
    COLECTIVA_INDICATORS,
    COLECTIVA_TREND,
    ROUGHERS,
    SCAVENGERS,
    VERTIMILLS,
    build_colectiva,
    map_colectiva_overview_store,
    map_colectiva_process_store,
    register_colectiva_callback,
)
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.ui.display_status import DisplayStatus

_END = datetime(2026, 4, 5, 4, tzinfo=UTC)
_START = _END - timedelta(hours=1)


def _entry(value: object) -> dict[str, object]:
    return {
        'status': 'ok',
        'value_kind': 'value',
        'value': str(value),
        'value_type': 'text',
        'parsed_value': str(value),
    }


def _store() -> dict[str, object]:
    values = {COLECTIVA_TREND.kpi_key: _entry('82.5')}
    for index, definition in enumerate(COLECTIVA_INDICATORS):
        values[definition.kpi_key] = _entry(str(index + 1))
    for index, definition in enumerate(ROUGHERS):
        values[definition.state_kpi_key] = _entry('Operando' if index % 2 else 'Detenido')
    for definition in SCAVENGERS:
        values[definition.state_kpi_key] = _entry('Detenido')
    for definition in VERTIMILLS:
        values[definition.state_kpi_key] = _entry('Operando')
        values[definition.amperage_kpi_key] = _entry('120')
    for group in BOMBAS:
        for definition in group:
            values[definition.state_kpi_key] = _entry('Detenido')
    values['numero_columnas_operando'] = _entry(10)
    values['numero_columnas_totales'] = _entry(14)
    return {
        'latest': {'values': values},
        'timeseries': {
            'end_utc': _END.isoformat(),
            'step_seconds': 120,
            'series': {
                COLECTIVA_TREND.kpi_key: {
                    'hours': 1,
                    'start_utc': _START.isoformat(),
                    'end_utc': _END.isoformat(),
                    'value_type': 'float',
                    'values': [None, 0.0, 82.5] + [None] * 27,
                }
            },
        },
    }


def _walk(item):
    if isinstance(item, Component):
        yield item
        yield from _walk(getattr(item, 'children', None))
    elif isinstance(item, (list, tuple)):
        for child in item:
            yield from _walk(child)


def test_definitions_legacy_keys_and_current_equipment_layout():
    assert COLECTIVA_TREND.kpi_key == 'recuperacion_cu_lab'
    assert [item.kpi_key for item in COLECTIVA_INDICATORS] == [
        'ley_cu_lab',
        'malla_325_lab',
        'malla_100_lab',
        'ley_concentrado_lab',
        'ley_colas_lab',
    ]
    assert [item.label for item in ROUGHERS] == [f'R{n}' for n in range(1, 10)]
    assert [item.label for item in SCAVENGERS] == ['SC1', 'SC2']
    assert [item.label for item in VERTIMILLS] == ['VT-009', 'VT-010', 'VT-701']
    assert [[item.label for item in group] for group in BOMBAS] == [
        ['PP45', 'PP46'],
        ['PP52', 'PP53'],
        ['PP855', 'PP856'],
    ]
    assert VERTIMILLS[2].amperage_kpi_key == 'amperaje_vertimil_701_inst'
    assert BOMBAS[2][1].state_kpi_key == 'estado_bomba856_inst'


def test_latest_values_and_timeseries_are_independent():
    store = _store()
    overview = map_colectiva_overview_store(store)
    process = map_colectiva_process_store(store)
    assert overview.trend_current.value == '82.5'
    assert [item.value.value for item in overview.indicators] == ['1', '2', '3', '4', '5']
    assert process.roughers[0].state.value == 'Detenido'
    assert process.roughers[1].state.value == 'Operando'
    assert process.vertimills[0].amperage.value == '120'
    assert process.bombas[2][1].state.value == 'Detenido'
    assert process.columns_operating.value == '10'
    assert process.columns_total.value == '14'
    assert overview.trend_history.status is DisplayStatus.OK
    assert len(overview.trend_history.points) == 30
    assert [point.value for point in overview.trend_history.points[:4]] == [None, 0.0, 82.5, None]
    assert overview.trend_history.points[-1].timestamp_utc == _END


def test_degraded_readings_do_not_become_detenido():
    store = _store()
    values = store['latest']['values']
    values.pop(ROUGHERS[0].state_kpi_key)
    values[SCAVENGERS[0].state_kpi_key] = {
        'status': 'missing',
        'value_kind': None,
        'value': None,
        'value_type': None,
        'parsed_value': None,
    }
    values[VERTIMILLS[0].state_kpi_key] = {
        'status': 'error',
        'value_kind': 'json',
        'value': None,
        'value_type': None,
        'parsed_value': None,
    }
    values[BOMBAS[0][0].state_kpi_key] = _entry('unrecognized')
    process = map_colectiva_process_store(store)
    assert process.roughers[0].state.status is DisplayStatus.NOT_MAPPED
    assert process.scavengers[0].state.status is DisplayStatus.EMPTY
    assert process.vertimills[0].state.status is DisplayStatus.ERROR
    root = build_colectiva(map_colectiva_overview_store(store), process)
    circles = [
        node
        for node in _walk(root)
        if 'ada-io-colectiva__circle' in (getattr(node, 'className', '') or '')
    ]
    assert len(circles) == 9
    invalid_icons = [
        node for node in _walk(root) if getattr(node, 'src', '').endswith('invalid-data.svg')
    ]
    assert invalid_icons


def test_bad_timeseries_does_not_affect_current_recovery():
    store = _store()
    store['timeseries']['series'][COLECTIVA_TREND.kpi_key]['values'][1] = 'bad'
    overview = map_colectiva_overview_store(store)
    assert overview.trend_history.status is DisplayStatus.INVALID
    assert overview.trend_current.value == '82.5'


def test_missing_timeseries_and_independent_latest_statuses():
    overview = map_colectiva_overview_store({'latest': {'values': {}}})
    process = map_colectiva_process_store({'latest': {'values': {}}})
    assert overview.trend_history.status is DisplayStatus.NOT_MAPPED
    assert all(item.value.status is DisplayStatus.NOT_MAPPED for item in overview.indicators)
    assert all(item.state.status is DisplayStatus.NOT_MAPPED for item in process.roughers)
    assert process.columns_operating.status is DisplayStatus.NOT_MAPPED
    assert process.columns_total.status is DisplayStatus.NOT_MAPPED


def test_each_mapped_kpi_is_inspectable():
    root = build_colectiva(
        map_colectiva_overview_store(_store()),
        map_colectiva_process_store(_store()),
    )
    nodes = [node for node in _walk(root) if getattr(node, 'data-kpi-inspection-key', None)]
    keys = [getattr(node, 'data-kpi-inspection-key') for node in nodes]
    expected = {COLECTIVA_TREND.kpi_key}
    expected.update(item.kpi_key for item in COLECTIVA_INDICATORS)
    expected.update(item.state_kpi_key for item in ROUGHERS + SCAVENGERS + VERTIMILLS)
    expected.update(item.amperage_kpi_key for item in VERTIMILLS)
    expected.update(item.state_kpi_key for group in BOMBAS for item in group)
    expected.update(('numero_columnas_operando', 'numero_columnas_totales'))
    assert set(keys) == expected
    assert len(keys) == len(set(keys))
    assert all(node.role == 'button' and node.tabIndex == 0 for node in nodes)


class DashStub:
    def __init__(self) -> None:
        self.args = None
        self.render = None

    def callback(self, *args):
        self.args = args

        def register(fn):
            self.render = fn
            return fn

        return register


def test_callback_reuses_flotacion_collector_store():
    app = DashStub()
    register_colectiva_callback(app, tool_key='integrated_operations')
    assert app.args[0].component_id == dashboard_card_content_id('colectiva')
    assert app.args[1].component_id == component_kpi_store_id(
        'integrated_operations', FLOTACION.tool_component_key
    )
    assert isinstance(app.render(_store()), Component)


def test_latest_validation_remains_independent_between_overview_and_process():
    store = _store()
    store['latest'] = {'values': None}
    overview = map_colectiva_overview_store(store)
    process = map_colectiva_process_store(store)
    assert overview.trend_current.status is DisplayStatus.INVALID
    assert all(item.value.status is DisplayStatus.INVALID for item in overview.indicators)
    assert all(item.state.status is DisplayStatus.INVALID for item in process.roughers)
    assert process.columns_operating.status is DisplayStatus.INVALID
    assert process.columns_total.status is DisplayStatus.INVALID
    assert overview.trend_history.status is DisplayStatus.OK
    assert overview.trend_history.points[1].value == 0.0
