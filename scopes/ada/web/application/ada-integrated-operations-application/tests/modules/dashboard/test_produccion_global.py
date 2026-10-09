from __future__ import annotations

from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import CHANCADO_STMG
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg import (
    register_chancado_stmg_callback,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.produccion_global import (
    PRODUCCION_GLOBAL_DEFINITIONS,
    build_produccion_global,
    map_produccion_global_store,
)
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.ui.display_status import DisplayStatus


def _entry(value: object, *, kind: str = 'value') -> dict[str, object]:
    return {'status': 'ok', 'value_kind': kind, 'value': value}


def _store(values: dict[str, object]) -> dict[str, object]:
    return {'latest': {'values': values}}


def _all_keys() -> tuple[str, ...]:
    return tuple(
        getattr(definition, attribute)
        for definition in PRODUCCION_GLOBAL_DEFINITIONS
        for attribute in (
            'real_key', 'plan_acumulado_key', 'proyeccion_key', 'plan_dia_key',
            'requerido_hora_key',
        )
    )


def _metrics(state):
    return tuple(
        getattr(row, name)
        for row in state.rows
        for name in ('real', 'plan_acumulado', 'proyeccion', 'plan_dia', 'requerido_hora')
    )


def _components(component):
    if isinstance(component, Component):
        yield component
        yield from _components(component.children)
    elif isinstance(component, list | tuple):
        for child in component:
            yield from _components(child)


def test_ten_independent_keys_and_decimal_text_are_preserved():
    keys = _all_keys()
    assert len(keys) == len(set(keys)) == 10
    state = map_produccion_global_store(_store({key: _entry('12,3') for key in keys}))
    assert [row.label for row in state.rows] == ['Alimentación', 'Transportado']
    assert tuple(item.kpi_key for item in _metrics(state)) == keys
    assert all(item.value.status is DisplayStatus.OK and item.value.value == '12,3'
               for item in _metrics(state))


def test_each_latest_status_is_isolated_without_json_fallback():
    keys = _all_keys()
    state = map_produccion_global_store(_store({
        keys[0]: _entry('14,5'),
        keys[1]: {'status': 'missing', 'value_kind': None, 'value': None},
        keys[2]: {'status': 'error', 'value_kind': 'value', 'value': None},
        keys[3]: _entry({'real': '6'}, kind='json'),
        keys[4]: _entry('  '),
        'produccion_global_summary_inst': _entry({'payload': []}, kind='json'),
    }))
    statuses = [metric.value.status for metric in _metrics(state)]
    assert statuses == [
        DisplayStatus.OK, DisplayStatus.EMPTY, DisplayStatus.ERROR,
        DisplayStatus.INVALID, DisplayStatus.INVALID,
        *([DisplayStatus.NOT_MAPPED] * 5),
    ]


def test_malformed_or_absent_latest_preserves_source_status():
    for store, expected in (
        ({'latest': None}, DisplayStatus.NOT_MAPPED),
        ({'latest': {'values': []}}, DisplayStatus.INVALID),
        (None, DisplayStatus.INVALID),
    ):
        state = map_produccion_global_store(store)
        assert all(metric.value.status is expected for metric in _metrics(state))


def test_invalid_scalar_type_does_not_leak_into_presentation():
    keys = _all_keys()
    for value in (12.3, True, None):
        state = map_produccion_global_store(_store({keys[0]: _entry(value)}))
        assert _metrics(state)[0].value.status is DisplayStatus.INVALID


def test_every_visible_metric_has_its_own_inspection_key_when_missing():
    state = map_produccion_global_store(_store({}))
    root = build_produccion_global(state)
    targets = [node for node in _components(root)
               if hasattr(node, 'data-kpi-inspection-key')]
    assert len(targets) == 10
    assert tuple(getattr(target, 'data-kpi-inspection-key') for target in targets) == _all_keys()
    assert all(target.tabIndex == 0 and target.role == 'button' for target in targets)
    assert all(target.children.to_plotly_json()['type'] == 'Img' for target in targets)


def test_values_in_pair_are_independently_inspectable():
    keys = _all_keys()
    root = build_produccion_global(
        map_produccion_global_store(_store({key: _entry(str(n)) for n, key in enumerate(keys)}))
    )
    targets = [node for node in _components(root)
               if hasattr(node, 'data-kpi-inspection-key')]
    assert [node.children for node in targets] == [str(n) for n in range(10)]
    assert targets[0].title == keys[0]
    assert targets[1].title == keys[1]


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


def test_chancado_stmg_callback_composes_global_before_existing_stockpile():
    stub = DashStub()
    register_chancado_stmg_callback(stub, tool_key='integrated_operations')
    root = stub.render(_store({}))
    assert stub.args[0].component_id == dashboard_card_content_id('chancado_stmg')
    assert stub.args[1].component_id == component_kpi_store_id(
        'integrated_operations', CHANCADO_STMG.tool_component_key,
    )
    assert len(root.children[2].children[1].children) == 2
