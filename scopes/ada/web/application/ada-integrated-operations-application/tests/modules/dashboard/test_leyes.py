from __future__ import annotations

import pytest
from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import CHANCADO_STMG
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg import (
    register_chancado_stmg_callback,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.decoder import (
    decode_chancado_stmg_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.leyes import (
    LEYES_DEFINITIONS,
    build_leyes_summary,
    map_leyes_readings,
)
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.ui.display_status import DisplayStatus

_PERIODS = ('hora', 'turno', 'dia', 'plan')
_EXPECTED = (
    ('ley_cu', 'Ley CuT %'),
    ('ley_mo', 'Ley Mo ppm'),
    ('ley_conc', 'Ley Conc %'),
    ('dureza', 'Dureza %'),
    ('recuperacion', 'Recuperación'),
    ('axb', 'AxB Alim'),
    ('arsenico', 'Arsénico ppm'),
)


def _entry(value: object, *, kind: str = 'value') -> dict[str, object]:
    return {
        'status': 'ok',
        'value_kind': kind,
        'value': value,
        'value_type': ('text' if kind == 'value' else None),
        'parsed_value': (value if isinstance(value, str) and kind == 'value' else None),
    }


def _store(values: dict[str, object]) -> dict[str, object]:
    return {'latest': {'values': values}}


def _metrics(state):
    return tuple(getattr(row, period) for row in state.rows for period in _PERIODS)


def _keys():
    return tuple(f'{prefix}_{period}' for prefix, _ in _EXPECTED for period in _PERIODS)


def _components(component):
    if isinstance(component, Component):
        yield component
        yield from _components(component.children)
    elif isinstance(component, list | tuple):
        for child in component:
            yield from _components(child)


def test_legacy_contract_has_seven_rows_and_28_distinct_individual_kpis():
    assert [(row.key, row.label) for row in LEYES_DEFINITIONS] == list(_EXPECTED)
    actual = tuple(
        getattr(row, f'{period}_key') for row in LEYES_DEFINITIONS for period in _PERIODS
    )
    assert actual == _keys()
    assert len(set(actual)) == 28


def test_every_scalar_value_is_preserved_without_rounding_or_replacement():
    values = {key: _entry(f'{index},123456789012345') for index, key in enumerate(_keys())}
    state = map_leyes_readings(decode_chancado_stmg_store(_store(values)))
    assert [metric.kpi_key for metric in _metrics(state)] == list(_keys())
    assert [metric.value.value for metric in _metrics(state)] == [
        f'{index},123456789012345' for index in range(28)
    ]
    assert all(metric.value.status is DisplayStatus.OK for metric in _metrics(state))


def test_latest_failures_are_independent_per_cell():
    first, second, third, fourth, fifth = _keys()[:5]
    state = map_leyes_readings(
        decode_chancado_stmg_store(_store(
            {
                first: _entry('12,34'),
                second: {
                    'status': 'missing',
                    'value_kind': None,
                    'value': None,
                    'value_type': None,
                    'parsed_value': None,
                },
                third: {
                    'status': 'error',
                    'value_kind': 'value',
                    'value': None,
                    'value_type': 'text',
                    'parsed_value': None,
                },
                fourth: _entry([1, 2], kind='json'),
                fifth: _entry('   '),
            }
        ))
    )
    assert [metric.value.status for metric in _metrics(state)] == [
        DisplayStatus.OK,
        DisplayStatus.EMPTY,
        DisplayStatus.ERROR,
        DisplayStatus.INVALID,
        DisplayStatus.INVALID,
        *([DisplayStatus.NOT_MAPPED] * 23),
    ]


@pytest.mark.parametrize(
    ('store', 'expected'),
    [
        (None, DisplayStatus.INVALID),
        ({'latest': None}, DisplayStatus.NOT_MAPPED),
        ({'latest': []}, DisplayStatus.INVALID),
        ({'latest': {'values': []}}, DisplayStatus.INVALID),
    ],
)
def test_absent_or_invalid_latest_keeps_source_status(store, expected):
    state = map_leyes_readings(decode_chancado_stmg_store(store))
    assert all(metric.value.status is expected for metric in _metrics(state))


@pytest.mark.parametrize('value', [True, None, {'foo': 'bar'}, ['1']])
def test_non_scalar_reading_is_invalid(value):
    first = _keys()[0]
    state = map_leyes_readings(decode_chancado_stmg_store(_store({first: _entry(value)})))
    assert _metrics(state)[0].value.status is DisplayStatus.INVALID


def test_table_preserves_28_inspectable_values_and_all_labels():
    keys = _keys()
    values = {key: _entry(f'{index},123456789012345') for index, key in enumerate(keys)}
    presentation = build_leyes_summary(map_leyes_readings(decode_chancado_stmg_store(_store(values))))
    components = tuple(_components(presentation))
    inspected = [item for item in components if hasattr(item, 'data-kpi-inspection-key')]
    assert [getattr(item, 'data-kpi-inspection-key') for item in inspected] == list(keys)
    assert [item.children for item in inspected] == [
        f'{index},123456789012345' for index in range(28)
    ]
    assert all(item.role == 'button' and item.tabIndex == 0 for item in inspected)
    assert all(item.title == key for item, key in zip(inspected, keys, strict=True))
    labels = [
        item
        for item in components
        if getattr(item, 'title', None) in {label for _, label in _EXPECTED}
    ]
    assert {item.children for item in labels} == {label for _, label in _EXPECTED}


def test_degraded_value_is_displayed_as_shared_status_icon():
    presentation = build_leyes_summary(map_leyes_readings(decode_chancado_stmg_store(_store({}))))
    inspected = [
        item for item in _components(presentation) if hasattr(item, 'data-kpi-inspection-key')
    ]
    assert len(inspected) == 28
    assert all(isinstance(item.children, Component) for item in inspected)


class DashStub:
    def __init__(self):
        self.arguments = None
        self.render = None

    def callback(self, *arguments):
        self.arguments = arguments

        def register(fn):
            self.render = fn
            return fn

        return register


def test_chancado_callback_renders_leyes_after_correas_with_same_store():
    app = DashStub()
    register_chancado_stmg_callback(app, tool_key='integrated_operations')
    assert app.arguments[0].component_id == dashboard_card_content_id('chancado_stmg')
    assert app.arguments[1].component_id == component_kpi_store_id(
        'integrated_operations', CHANCADO_STMG.tool_component_key
    )
    store = _store({_keys()[0]: _entry('12,3456789')})
    root = app.render(store)
    last = root.children[-1]
    inspected = [item for item in _components(last) if hasattr(item, 'data-kpi-inspection-key')]
    assert len(root.children) == 6
    assert len(inspected) == 28
    assert inspected[0].children == '12,3456789'
