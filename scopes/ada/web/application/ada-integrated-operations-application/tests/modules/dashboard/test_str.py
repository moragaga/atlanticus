from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import (
    TRANSPORTE_FLUIDOS,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.str import (
    DUCTOS,
    STR_ESPESADORES,
    STR_TREND,
    build_str,
    map_str_ductos_store,
    map_str_espesadores_store,
    map_str_overview_store,
    register_str_callback,
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
    values = {STR_TREND.kpi_key: _entry('345.6')}
    for index, tank in enumerate(STR_ESPESADORES):
        values[tank.state_kpi_key] = _entry('Operando')
        values[tank.feed_kpi_key] = _entry('Alimentando' if index == 0 else 'No Alimentando')
        for metric in tank.metrics:
            values[metric.kpi_key] = _entry('50')
    for duct in DUCTOS:
        values[duct.state_kpi_key] = _entry('Detenido')
        values[duct.solids_in_kpi_key] = _entry('42.3')
        values[duct.solids_out_kpi_key] = _entry('50.2')
        for pump in duct.pumps:
            values[pump.state_kpi_key] = _entry('Operando')
    return {
        'latest': {'values': values},
        'timeseries': {
            'step_seconds': 120,
            'end_utc': _END.isoformat(),
            'series': {
                STR_TREND.kpi_key: {
                    'hours': 1,
                    'start_utc': _START.isoformat(),
                    'end_utc': _END.isoformat(),
                    'value_type': 'float',
                    'values': [None, 0.0, 9.5] + [None] * 27,
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


def test_old_trend_and_current_equipment_contracts():
    assert (STR_TREND.label, STR_TREND.kpi_key, STR_TREND.unit) == (
        'Relave',
        'relave_real_mean_hora',
        't/h',
    )
    assert [item.label for item in STR_ESPESADORES] == ['TK-50', 'TK-51', 'TK-712']
    for tank, code in zip(STR_ESPESADORES, ('050', '051', '712'), strict=True):
        assert tank.state_kpi_key == f'estado_tk_{code}_inst'
        assert tank.feed_kpi_key == f'estado_alimentacion_tk_{code}_inst'
        assert [item.kpi_key for item in tank.metrics] == [
            f'altura_tk_{code}_inst',
            f'torque_tk_{code}_inst',
            f'pendiente_tk_{code}_inst',
            f'interfaz_tk_{code}_inst',
        ]
    assert [item.label for item in DUCTOS] == ['36', '28']
    assert [[pump.label for pump in duct.pumps] for duct in DUCTOS] == [
        ['PP003', 'PP004', 'PP1005'],
        ['PP1010', 'PP1011'],
    ]


def test_latest_mappings_preserve_independent_state_and_numbers():
    overview = map_str_overview_store(_store())
    tanks = map_str_espesadores_store(_store())
    ducts = map_str_ductos_store(_store())
    assert overview.current.value == '345.6'
    assert [item.feed.value for item in tanks] == ['operando', 'detenido', 'detenido']
    assert len(tanks) == 3
    assert [item.value.value for item in tanks[0].metrics] == ['50'] * 4
    assert [(item.solids_in.value, item.solids_out.value) for item in ducts] == [
        ('42.3', '50.2'),
        ('42.3', '50.2'),
    ]
    assert [len(item.pumps) for item in ducts] == [3, 2]


def test_history_null_samples_and_utc_bounds():
    history = map_str_overview_store(_store()).history
    assert history.status is DisplayStatus.OK
    assert len(history.points) == 30
    assert [point.value for point in history.points[:4]] == [None, 0.0, 9.5, None]
    assert history.points[0].timestamp_utc == _START + timedelta(seconds=120)
    assert history.points[-1].timestamp_utc == _END


def test_invalid_history_does_not_invalidate_latest():
    data = _store()
    data['timeseries']['series'][STR_TREND.kpi_key]['values'][1] = 'bad'
    reading = map_str_overview_store(data)
    assert reading.history.status is DisplayStatus.INVALID
    assert reading.current.value == '345.6'


def test_missing_and_unknown_states_are_not_operando_or_detenido():
    data = _store()
    values = data['latest']['values']
    values.pop(STR_ESPESADORES[0].feed_kpi_key)
    values[STR_ESPESADORES[1].feed_kpi_key] = {
        'status': 'missing',
        'value_kind': None,
        'value': None,
        'value_type': None,
        'parsed_value': None,
    }
    values[STR_ESPESADORES[2].feed_kpi_key] = _entry('another state')
    values[DUCTOS[0].state_kpi_key] = _entry('unknown')
    values.pop(DUCTOS[1].state_kpi_key)
    values[DUCTOS[0].pumps[0].state_kpi_key] = {
        'status': 'error',
        'value_kind': 'json',
        'value': None,
        'value_type': None,
        'parsed_value': None,
    }
    tanks = map_str_espesadores_store(data)
    ducts = map_str_ductos_store(data)
    assert [item.feed.status for item in tanks] == [
        DisplayStatus.NOT_MAPPED,
        DisplayStatus.EMPTY,
        DisplayStatus.INVALID,
    ]
    assert ducts[0].state.value == 'unknown'
    assert ducts[1].state.status is DisplayStatus.NOT_MAPPED
    assert ducts[0].pumps[0].state.status is DisplayStatus.ERROR
    assert ducts[0].pumps[1].state.status is DisplayStatus.OK


def test_degraded_metric_and_missing_delivery_are_independent():
    data = _store()
    data['latest']['values'].pop(STR_ESPESADORES[1].metrics[0].kpi_key)
    data['latest']['values'][DUCTOS[0].solids_in_kpi_key] = {
        'status': 'error',
        'value_kind': 'json',
        'value': None,
        'value_type': None,
        'parsed_value': None,
    }
    assert map_str_espesadores_store(data)[1].metrics[0].value.status is DisplayStatus.NOT_MAPPED
    assert map_str_ductos_store(data)[0].solids_in.status is DisplayStatus.ERROR
    assert (
        map_str_overview_store({'latest': {'values': {}}}).history.status
        is DisplayStatus.NOT_MAPPED
    )


def test_all_latest_keys_are_inspectable_once():
    root = build_str(
        map_str_overview_store(_store()),
        map_str_espesadores_store(_store()),
        map_str_ductos_store(_store()),
    )
    nodes = [node for node in _walk(root) if getattr(node, 'data-kpi-inspection-key', None)]
    keys = [getattr(node, 'data-kpi-inspection-key') for node in nodes]
    expected = {STR_TREND.kpi_key}
    for tank in STR_ESPESADORES:
        expected.update((tank.state_kpi_key, tank.feed_kpi_key))
        expected.update(metric.kpi_key for metric in tank.metrics)
    for duct in DUCTOS:
        expected.update((duct.state_kpi_key, duct.solids_in_kpi_key, duct.solids_out_kpi_key))
        expected.update(pump.state_kpi_key for pump in duct.pumps)
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


def test_callback_uses_transporte_fluidos_store():
    app = DashStub()
    register_str_callback(app, tool_key='integrated_operations')
    assert app.args[0].component_id == dashboard_card_content_id('str')
    assert app.args[1].component_id == component_kpi_store_id(
        'integrated_operations', TRANSPORTE_FLUIDOS.tool_component_key
    )
    assert isinstance(app.render(_store()), Component)
