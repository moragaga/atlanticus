from __future__ import annotations

import pytest

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import CHANCADO_STMG
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg import (
    register_chancado_stmg_callback,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.stockpile_mina import (
    STOCKPILE_MINA_KPI_KEYS,
    STOCKPILE_MINA_SCALE_MAX_M,
    map_stockpile_mina_store,
)
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.ui.display_status import DisplayStatus
from ada.web.ui.stockpile import ADA_STOCKPILE_ASSET_LAYER


def _entry(value: str) -> dict[str, object]:
    return {'status': 'ok', 'value_kind': 'value', 'value': value}


def _store(values: dict[str, object]) -> dict[str, object]:
    return {'latest': {'values': values}}


def _values() -> dict[str, object]:
    return {
        STOCKPILE_MINA_KPI_KEYS[0][2]: _entry('65'),
        STOCKPILE_MINA_KPI_KEYS[0][3]: _entry('18,2'),
        STOCKPILE_MINA_KPI_KEYS[1][2]: _entry('80'),
        STOCKPILE_MINA_KPI_KEYS[1][3]: _entry('23,5'),
    }


def test_mina_stockpile_preserves_independent_source_text_and_common_scale() -> None:
    state = map_stockpile_mina_store(_store(_values()))

    assert len(state.items) == 2
    assert [item.label for item in state.items] == ['Pila 1', 'Pila 2']
    assert [item.percentage.value for item in state.items] == ['65', '80']
    assert [item.height_m.value for item in state.items] == ['18,2', '23,5']
    assert state.scale_max_m == STOCKPILE_MINA_SCALE_MAX_M == 28


@pytest.mark.parametrize(
    ('store', 'expected'),
    [
        ({'latest': None}, DisplayStatus.NOT_MAPPED),
        ({'latest': {'values': 'broken'}}, DisplayStatus.INVALID),
        (None, DisplayStatus.INVALID),
    ],
)
def test_absent_or_invalid_component_store_preserves_both_pile_states(store, expected):
    state = map_stockpile_mina_store(store)

    assert all(item.percentage.status is expected for item in state.items)
    assert all(item.height_m.status is expected for item in state.items)


def test_mina_stockpile_statuses_are_per_reading_and_per_pile() -> None:
    values = _values()
    values[STOCKPILE_MINA_KPI_KEYS[0][2]] = {'status': 'missing', 'value_kind': None, 'value': None}
    values[STOCKPILE_MINA_KPI_KEYS[1][3]] = {
        'status': 'error',
        'value_kind': 'value',
        'value': None,
    }
    state = map_stockpile_mina_store(_store(values))

    assert state.items[0].percentage.status is DisplayStatus.EMPTY
    assert state.items[0].height_m.status is DisplayStatus.OK
    assert state.items[1].percentage.status is DisplayStatus.OK
    assert state.items[1].height_m.status is DisplayStatus.ERROR


def test_unmapped_kpi_and_malformed_value_do_not_affect_other_readings() -> None:
    values = _values()
    del values[STOCKPILE_MINA_KPI_KEYS[0][3]]
    values[STOCKPILE_MINA_KPI_KEYS[1][2]] = {
        'status': 'ok',
        'value_kind': 'json',
        'value': {'a': 2},
    }
    state = map_stockpile_mina_store(_store(values))

    assert state.items[0].height_m.status is DisplayStatus.NOT_MAPPED
    assert state.items[0].percentage.value == '65'
    assert state.items[1].percentage.status is DisplayStatus.INVALID
    assert state.items[1].height_m.value == '23,5'


def test_number_instead_of_text_is_invalid_at_collector_boundary() -> None:
    values = _values()
    values[STOCKPILE_MINA_KPI_KEYS[0][3]] = _entry(18.2)
    state = map_stockpile_mina_store(_store(values))

    assert state.items[0].height_m.status is DisplayStatus.INVALID


class DashStub:
    def __init__(self) -> None:
        self.callback_args = None
        self.callback_function = None

    def callback(self, *args):
        self.callback_args = args

        def register(function):
            self.callback_function = function
            return function

        return register


def test_mina_stockpile_callback_consumes_existing_component_store():
    stub = DashStub()
    register_chancado_stmg_callback(stub, tool_key='integrated_operations')

    result = stub.callback_function(_store(_values()))

    assert stub.callback_args[0].component_id == dashboard_card_content_id('chancado_stmg')
    assert stub.callback_args[1].component_id == component_kpi_store_id(
        'integrated_operations', CHANCADO_STMG.tool_component_key
    )
    assert result is not None
    assert result.to_plotly_json()['type'] == 'Div'


def test_stockpile_layer_can_be_composed_by_dashboard():
    from ada.web.application.integrated_operations.modules.dashboard.module import (
        create_dashboard_module,
    )

    module = create_dashboard_module(None)

    assert ADA_STOCKPILE_ASSET_LAYER in module.asset_layers
