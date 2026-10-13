from __future__ import annotations

import pytest

from ada.contracts.tools.enums import ToolScope
from ada.web.application.integrated_operations.modules.dashboard.global_indicators import (
    DashboardGlobalIndicatorBinding,
    DashboardGlobalIndicatorsRuntimeBinding,
    resolve_dashboard_global_indicators,
    resolve_dashboard_global_indicators_runtime_state,
)
from ada.web.content_state import ContentState
from ada.web.ui.display_status import DisplayStatus
from ada.web.ui.global_indicator import (
    GlobalIndicatorDefinition,
    GlobalIndicatorLastMeasurementDefinition,
    GlobalIndicatorMeasurementDefinition,
)


def _binding() -> DashboardGlobalIndicatorsRuntimeBinding:
    definition = GlobalIndicatorDefinition(
        key='global',
        label='Global',
        unit='kt',
        measurements=(
            GlobalIndicatorMeasurementDefinition(
                key='day',
                label='Día',
                actual_kpi_key='global.day.actual',
                plan_kpi_key='global.day.plan',
                color_kpi_key='global.day.color',
            ),
            GlobalIndicatorMeasurementDefinition(
                key='week',
                label='Semana',
                actual_kpi_key='global.week.actual',
                plan_kpi_key='global.week.plan',
            ),
        ),
        last_measurement=GlobalIndicatorLastMeasurementDefinition(kpi_key='global.latest'),
    )
    return DashboardGlobalIndicatorsRuntimeBinding(
        tool_key='integrated_operations',
        indicators=(DashboardGlobalIndicatorBinding(definition, (ToolScope.MINE,)),),
    )


def _value(value: str, *, parsed: str | None = None) -> dict[str, object]:
    return {
        'status': 'ok',
        'value_kind': 'value',
        'value_type': 'text',
        'value': value,
        'parsed_value': value if parsed is None else parsed,
    }


def _store() -> dict[str, object]:
    return {
        'tool_key': 'integrated_operations',
        'destination_key': 'global_indicators',
        'latest': {
            'manifest': {'revision': 'r1'},
            'values': {
                'global.day.actual': _value('1234.5', parsed='1.234,5'),
                'global.day.plan': _value('1250', parsed='1.250'),
                'global.day.color': _value('indicator-positive', parsed='color-formatted'),
                'global.week.actual': _value('5000'),
                'global.week.plan': _value('5200'),
                'global.latest': _value('1210.1', parsed='1.210,1'),
            },
        },
        'timeseries': None,
    }


def _state(store_data: object):
    return resolve_dashboard_global_indicators(store_data, binding=_binding())[0].state


def test_system_store_exposes_formatted_values_and_raw_color() -> None:
    state = _state(_store())

    assert state.measurements[0].actual_value.status is DisplayStatus.OK
    assert state.measurements[0].actual_value.value == '1.234,5'
    assert state.measurements[0].plan_value.value == '1.250'
    assert state.measurements[0].color_class == 'indicator-positive'
    assert state.last_measurement is not None
    assert state.last_measurement.actual_value.value == '1.210,1'
    assert state.measurements[0].actual_kpi_key == 'global.day.actual'
    assert resolve_dashboard_global_indicators_runtime_state(
        _store(), binding=_binding()
    ) is ContentState.READY


@pytest.mark.parametrize('field', ('tool_key', 'destination_key'))
def test_system_store_rejects_other_tool_or_destination(field: str) -> None:
    store = _store()
    store[field] = 'unrelated'

    state = _state(store)
    assert all(
        value.status is DisplayStatus.INVALID
        for measurement in state.measurements
        for value in (measurement.actual_value, measurement.plan_value)
    )
    assert resolve_dashboard_global_indicators_runtime_state(
        store, binding=_binding()
    ) is ContentState.SOURCE_ERROR


@pytest.mark.parametrize(
    ('store_data', 'expected'),
    [
        (None, DisplayStatus.INVALID),
        ({'tool_key': 'integrated_operations', 'destination_key': 'global_indicators', 'latest': None}, DisplayStatus.NOT_MAPPED),
        ({'tool_key': 'integrated_operations', 'destination_key': 'global_indicators', 'latest': {'values': []}}, DisplayStatus.INVALID),
    ],
)
def test_source_status_follows_system_latest_contract(store_data: object, expected: DisplayStatus) -> None:
    state = _state(store_data)

    assert state.measurements[0].actual_value.status is expected
    assert state.measurements[1].plan_value.status is expected
    assert resolve_dashboard_global_indicators_runtime_state(
        store_data, binding=_binding()
    ) is ContentState.SOURCE_ERROR


@pytest.mark.parametrize(
    ('entry', 'expected'),
    [
        (None, DisplayStatus.NOT_MAPPED),
        ({'status': 'missing', 'value_kind': None, 'value': None, 'value_type': None, 'parsed_value': None}, DisplayStatus.EMPTY),
        ({'status': 'error', 'value_kind': 'value', 'value': None, 'value_type': 'text', 'parsed_value': None}, DisplayStatus.ERROR),
        ({'status': 'ok', 'value_kind': 'json', 'value': {'x': 1}, 'value_type': None, 'parsed_value': None}, DisplayStatus.INVALID),
    ],
)
def test_individual_kpi_status_is_preserved(entry: object, expected: DisplayStatus) -> None:
    store = _store()
    values = store['latest']['values']
    if entry is None:
        del values['global.day.actual']
    else:
        values['global.day.actual'] = entry

    state = _state(store)
    assert state.measurements[0].actual_value.status is expected
    assert state.measurements[0].plan_value.status is DisplayStatus.OK
    assert state.measurements[1].actual_value.status is DisplayStatus.OK
    assert resolve_dashboard_global_indicators_runtime_state(
        store, binding=_binding()
    ) is ContentState.SOURCE_ERROR


def test_unavailable_color_does_not_remove_valid_measurements() -> None:
    store = _store()
    store['latest']['values']['global.day.color'] = _value('')

    state = _state(store)
    assert state.measurements[0].actual_value.status is DisplayStatus.OK
    assert state.measurements[0].color_class is None
    assert resolve_dashboard_global_indicators_runtime_state(
        store, binding=_binding()
    ) is ContentState.SOURCE_ERROR
