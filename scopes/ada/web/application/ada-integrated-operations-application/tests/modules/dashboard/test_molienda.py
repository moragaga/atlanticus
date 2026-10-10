from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import MOLIENDA
from ada.web.application.integrated_operations.modules.dashboard.plant.molienda import (
    MOLIENDA_GENERAL_METRICS,
    MOLIENDA_LINES,
    MOLIENDA_TREND,
    build_molienda,
    map_molienda_overview_readings,
    map_molienda_sags_readings,
    register_molienda_callback,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.molienda.decoder import (
    decode_molienda_store,
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
    values = {MOLIENDA_TREND.kpi_key: _entry('234.5')}
    for index, metric in enumerate(MOLIENDA_GENERAL_METRICS):
        values[metric.kpi_key] = _entry(str(index + 10))
    for line in MOLIENDA_LINES:
        values[line.sag.state_kpi_key] = _entry('Operando')
        values[line.sag.power_kpi_key] = _entry('1500')
        for mill in line.mills:
            values[mill.state_kpi_key] = _entry('Detenido')
            values[mill.power_kpi_key] = _entry('500')
        for metric in line.metrics:
            values[metric.kpi_key] = _entry('7')
    return {
        'latest': {'values': values},
        'timeseries': {
            'end_utc': _END.isoformat(),
            'step_seconds': 120,
            'series': {
                MOLIENDA_TREND.kpi_key: {
                    'hours': 1,
                    'start_utc': _START.isoformat(),
                    'end_utc': _END.isoformat(),
                    'value_type': 'float',
                    'values': [None, 0.0, 4.5] + [None] * 27,
                }
            },
        },
    }


def _overview(source: object):
    values, timeseries = decode_molienda_store(source)
    return map_molienda_overview_readings(values, timeseries)


def _sags(source: object):
    values, _ = decode_molienda_store(source)
    return map_molienda_sags_readings(values)


def _walk(item):
    if isinstance(item, Component):
        yield item
        yield from _walk(getattr(item, 'children', None))
    elif isinstance(item, list | tuple):
        for child in item:
            yield from _walk(child)


def test_legacy_kpi_contract_and_four_sag_line_associations():
    assert MOLIENDA_TREND.kpi_key == 'rendimiento_real_mean_hora'
    assert [item.kpi_key for item in MOLIENDA_GENERAL_METRICS] == [
        'avance_pebbles_real',
        'recirculacion_pebbles_mean_hora',
        'cee_planta_mean_hora',
        'p80_planta_real',
    ]
    assert [line.number for line in MOLIENDA_LINES] == [1, 2, 3, 4]
    assert [[mill.label for mill in line.mills] for line in MOLIENDA_LINES] == [
        ['MB-004', 'MB-005'],
        ['MB-006', 'MB-007'],
        ['MB-008', 'MB-009'],
        ['MB-010'],
    ]
    assert [item.label for item in MOLIENDA_LINES[0].metrics] == ['F80', 'P80', 'Rend.']


def test_latest_independent_values_and_operational_states():
    state = _overview(_store())
    assert state.trend_current.value == '234.5'
    assert [item.value.value for item in state.general] == ['10', '11', '12', '13']
    lines = _sags(_store())
    assert lines[0].sag.state.value == 'Operando'
    assert lines[0].sag.power.value == '1500'
    assert [mill.state.value for mill in lines[0].mills] == ['Detenido', 'Detenido']
    assert len(lines[3].mills) == 1


def test_timeseries_preserves_exact_numeric_and_null_samples():
    state = _overview(_store())
    history = state.trend_history
    assert history.status is DisplayStatus.OK
    assert len(history.points) == 30
    assert [item.value for item in history.points[:4]] == [None, 0.0, 4.5, None]
    assert history.points[0].timestamp_utc == _START + timedelta(seconds=120)
    assert history.points[-1].timestamp_utc == _END
    data = _store()
    data['timeseries']['series'][MOLIENDA_TREND.kpi_key]['values'] = [None] * 30
    assert all(item.value is None for item in _overview(data).trend_history.points)


def test_degraded_states_are_independent_and_not_replaced_by_detenido():
    data = _store()
    values = data['latest']['values']
    values.pop(MOLIENDA_LINES[0].sag.state_kpi_key)
    values[MOLIENDA_LINES[0].mills[0].power_kpi_key] = {
        'status': 'error',
        'value_kind': 'value',
        'value': None,
        'value_type': 'text',
        'parsed_value': None,
    }
    values[MOLIENDA_GENERAL_METRICS[2].kpi_key] = {
        'status': 'missing',
        'value_kind': None,
        'value': None,
        'value_type': None,
        'parsed_value': None,
    }
    state = _overview(data)
    lines = _sags(data)
    assert lines[0].sag.state.status is DisplayStatus.NOT_MAPPED
    assert lines[0].sag.power.status is DisplayStatus.OK
    assert lines[0].mills[0].power.status is DisplayStatus.ERROR
    assert lines[0].mills[1].power.status is DisplayStatus.OK
    assert state.general[2].value.status is DisplayStatus.EMPTY


def test_invalid_timeseries_does_not_disrupt_latest_values():
    data = _store()
    data['timeseries']['series'][MOLIENDA_TREND.kpi_key]['values'][3] = 'fake'
    state = _overview(data)
    assert state.trend_history.status is DisplayStatus.INVALID
    assert state.trend_current.status is DisplayStatus.OK
    assert all(reading.value.status is DisplayStatus.OK for reading in state.general)


def test_missing_delivery_keeps_empty_trend_and_independent_statuses():
    state = _overview({'latest': {'values': {}}})
    assert state.trend_history.status is DisplayStatus.NOT_MAPPED
    assert state.trend_history.points == ()
    assert all(metric.value.status is DisplayStatus.NOT_MAPPED for metric in state.general)
    lines = _sags({'latest': {'values': {}}})
    assert all(line.sag.state.status is DisplayStatus.NOT_MAPPED for line in lines)


def test_readings_are_inspectable_without_inventing_extra_kpi_keys():
    source = _store()
    values, timeseries = decode_molienda_store(source)
    root = build_molienda(
        map_molienda_overview_readings(values, timeseries), map_molienda_sags_readings(values)
    )
    targets = [node for node in _walk(root) if getattr(node, 'data-kpi-inspection-key', None)]
    keys = [getattr(node, 'data-kpi-inspection-key') for node in targets]
    expected = [MOLIENDA_TREND.kpi_key]
    expected.extend(metric.kpi_key for metric in MOLIENDA_GENERAL_METRICS)
    for line in MOLIENDA_LINES:
        expected.extend((line.sag.state_kpi_key, line.sag.power_kpi_key))
        expected.extend(metric.kpi_key for metric in line.metrics)
        for mill in line.mills:
            expected.extend((mill.state_kpi_key, mill.power_kpi_key))
    assert set(keys) == set(expected)
    assert len(keys) == len(set(keys))
    assert all(node.role == 'button' and node.tabIndex == 0 for node in targets)


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


def test_callback_uses_existing_molienda_component_store():
    dash_app = DashStub()
    register_molienda_callback(dash_app, tool_key='integrated_operations')
    assert dash_app.args[0].component_id == dashboard_card_content_id('molienda')
    assert dash_app.args[1].component_id == component_kpi_store_id(
        'integrated_operations', MOLIENDA.tool_component_key
    )
    assert isinstance(dash_app.render(_store()), Component)
