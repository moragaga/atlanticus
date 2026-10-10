from __future__ import annotations

import pytest

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import CHANCADO_STMG
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg import (
    register_chancado_stmg_callback,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.stockpile import (
    STOCKPILE_MINA_DEFINITIONS,
    STOCKPILE_MINA_KPI_KEYS,
    STOCKPILE_MINA_SCALE_MAX_M,
    map_stockpile_mina_store,
)
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.ui.display_status import DisplayStatus
from ada.web.ui.stockpile import ADA_STOCKPILE_ASSET_LAYER, StockpileVariant


def _entry(value: str) -> dict[str, object]:
    return {'status': 'ok', 'value_kind': 'value', 'value': value}


def _store(values: dict[str, object]) -> dict[str, object]:
    return {'latest': {'values': values}}


def _values() -> dict[str, object]:
    return {
        STOCKPILE_MINA_KPI_KEYS[0][1]: _entry('65'),
        STOCKPILE_MINA_KPI_KEYS[0][2]: _entry('18,2'),
        STOCKPILE_MINA_KPI_KEYS[1][1]: _entry('80'),
        STOCKPILE_MINA_KPI_KEYS[1][2]: _entry('23,5'),
    }


def test_mina_maps_two_independent_readings_to_individual_definitions():
    readings = map_stockpile_mina_store(_store(_values()))
    assert len(readings) == len(STOCKPILE_MINA_DEFINITIONS) == 2
    assert [r.percent.value for r in readings] == ['65', '80']
    assert [r.height_m.value for r in readings] == ['18,2', '23,5']
    assert all(d.variant is StockpileVariant.VARIABLE_HEIGHT for d in STOCKPILE_MINA_DEFINITIONS)
    assert all(
        d.scale_max_m == STOCKPILE_MINA_SCALE_MAX_M == 28 for d in STOCKPILE_MINA_DEFINITIONS
    )


@pytest.mark.parametrize(
    'store, expected',
    [
        ({'latest': None}, DisplayStatus.NOT_MAPPED),
        ({'latest': {'values': 'broken'}}, DisplayStatus.INVALID),
        (None, DisplayStatus.INVALID),
    ],
)
def test_bad_component_store_preserves_errors_per_pile(store, expected):
    readings = map_stockpile_mina_store(store)
    assert all(r.percent.status is expected and r.height_m.status is expected for r in readings)


def test_mina_handles_partial_readings_without_affecting_other_pile():
    values = _values()
    values[STOCKPILE_MINA_KPI_KEYS[0][1]] = {'status': 'missing', 'value_kind': None, 'value': None}
    values[STOCKPILE_MINA_KPI_KEYS[1][2]] = {
        'status': 'error',
        'value_kind': 'value',
        'value': None,
    }
    readings = map_stockpile_mina_store(_store(values))
    assert readings[0].percent.status is DisplayStatus.EMPTY
    assert readings[0].height_m.status is DisplayStatus.OK
    assert readings[1].percent.status is DisplayStatus.OK
    assert readings[1].height_m.status is DisplayStatus.ERROR


def test_numbers_are_not_accepted_at_collector_boundary():
    values = _values()
    values[STOCKPILE_MINA_KPI_KEYS[0][2]] = _entry(18.2)
    readings = map_stockpile_mina_store(_store(values))
    assert readings[0].height_m.status is DisplayStatus.INVALID


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


def test_callback_rebuilds_two_images_from_existing_kpi_store():
    stub = DashStub()
    register_chancado_stmg_callback(stub, tool_key='integrated_operations')
    result = stub.callback_function(_store(_values()))
    assert stub.callback_args[0].component_id == dashboard_card_content_id('chancado_stmg')
    assert stub.callback_args[1].component_id == component_kpi_store_id(
        'integrated_operations', CHANCADO_STMG.tool_component_key
    )
    assert result.to_plotly_json()['type'] == 'Div'
    assert len(result.children[2].children[1].children) == 2


def test_dashboard_retains_stockpile_asset_layer():
    from ada.web.application.integrated_operations.modules.dashboard.module import (
        create_dashboard_module,
    )

    assert ADA_STOCKPILE_ASSET_LAYER in create_dashboard_module(None).asset_layers
