from __future__ import annotations

from dataclasses import replace

import pytest

from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.correas_stmg import (
    CORREAS_STMG_DEFINITIONS,
    CORREAS_STMG_METRIC,
    map_correas_stmg_store,
)
from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)
from ada.web.ui.display_status import DisplayStatus


def _entry(value: object, *, kind: str = 'value') -> dict[str, object]:
    return {'status': 'ok', 'value_kind': kind, 'value': value}


def _store(values: dict[str, object]) -> dict[str, object]:
    return {'latest': {'values': values}}


def test_three_independent_belts_and_metric_keep_values():
    a, b, c = CORREAS_STMG_DEFINITIONS
    state = map_correas_stmg_store(
        _store({
            a.state_kpi_key: _entry('operando'),
            b.state_kpi_key: _entry('detenido'),
            c.state_kpi_key: _entry('OPERANDO'),
            CORREAS_STMG_METRIC.value_kpi_key: _entry('123,45'),
        }),
        CORREAS_STMG_DEFINITIONS,
        CORREAS_STMG_METRIC,
    )
    assert [x.value for x in state.states] == ['operando', 'detenido', 'operando']
    assert state.metric.value == '123,45'
    assert state.metric_color is None


def test_errors_are_independent_and_unknown_state_is_invalid():
    a, b, c = CORREAS_STMG_DEFINITIONS
    state = map_correas_stmg_store(
        _store({
            a.state_kpi_key: _entry('mantencion'),
            b.state_kpi_key: {'status': 'error', 'value_kind': 'value', 'value': None},
            c.state_kpi_key: _entry('detenido'),
        }),
        CORREAS_STMG_DEFINITIONS,
        CORREAS_STMG_METRIC,
    )
    assert [x.status for x in state.states] == [
        DisplayStatus.INVALID, DisplayStatus.ERROR, DisplayStatus.OK,
    ]
    assert state.metric.status is DisplayStatus.NOT_MAPPED


@pytest.mark.parametrize('store, expected', [
    (None, DisplayStatus.INVALID),
    ({'latest': None}, DisplayStatus.NOT_MAPPED),
    ({'latest': {'values': []}}, DisplayStatus.INVALID),
])
def test_invalid_component_store_is_not_silenced(store, expected):
    state = map_correas_stmg_store(store, CORREAS_STMG_DEFINITIONS, CORREAS_STMG_METRIC)
    assert all(reading.status is expected for reading in state.states)
    assert state.metric.status is expected


@pytest.mark.parametrize(('code', 'expected'), [
    ('0', DashboardValueStatus.NEUTRAL),
    ('1', DashboardValueStatus.DANGER),
    ('2', DashboardValueStatus.WARNING),
])
def test_optional_color_is_independent_of_value(code, expected):
    metric = replace(CORREAS_STMG_METRIC, color_kpi_key='transportado_stmg_color_inst')
    state = map_correas_stmg_store(
        _store({metric.value_kpi_key: _entry('154'), metric.color_kpi_key: _entry(code)}),
        CORREAS_STMG_DEFINITIONS,
        metric,
    )
    assert state.metric.value == '154'
    assert state.metric_color.value is expected


def test_color_failure_preserves_metric_and_reports_failure():
    metric = replace(CORREAS_STMG_METRIC, color_kpi_key='transportado_stmg_color_inst')
    state = map_correas_stmg_store(
        _store({
            metric.value_kpi_key: _entry('154'),
            metric.color_kpi_key: {'status': 'error', 'value_kind': 'value', 'value': None},
        }),
        CORREAS_STMG_DEFINITIONS,
        metric,
    )
    assert state.metric.status is DisplayStatus.OK
    assert state.metric_color.status is DisplayStatus.ERROR


def test_duplicate_kpi_keys_rejected():
    metric = replace(CORREAS_STMG_METRIC, value_kpi_key=CORREAS_STMG_DEFINITIONS[0].state_kpi_key)
    with pytest.raises(ValueError, match='distinct'):
        map_correas_stmg_store(_store({}), CORREAS_STMG_DEFINITIONS, metric)
