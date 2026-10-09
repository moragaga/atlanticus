from __future__ import annotations

import pytest
from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import (
    STOCKPILE_CHACAY,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay import (
    STOCKPILE_CHACAY_PILES,
    STOCKPILE_CHACAY_POSITION_KEY,
    STOCKPILE_CHACAY_ROWS,
    build_stockpile_chacay,
    map_stockpile_chacay_store,
    register_stockpile_chacay_callback,
)
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.ui.display_status import DisplayStatus
from ada.web.ui.stockpile import StockpileVariant


def _entry(value: object) -> dict[str, object]:
    return {'status': 'ok', 'value_kind': 'value', 'value': value}


def _store(values: dict[str, object]) -> dict[str, object]:
    return {'latest': {'values': values}}


def _components(item):
    if isinstance(item, Component):
        yield item
        yield from _components(item.children)
    elif isinstance(item, list | tuple):
        for child in item:
            yield from _components(child)


def test_current_keys_for_four_piles_four_rows_and_position():
    assert STOCKPILE_CHACAY_POSITION_KEY == 'posicion_carro'
    assert [(pile.label, pile.kpi_key) for pile in STOCKPILE_CHACAY_PILES] == [
        ('G', 'nivel_pila_G_stock'),
        ('H', 'nivel_pila_H_stock'),
        ('I', 'nivel_pila_I_stock'),
        ('J', 'nivel_pila_J_stock'),
    ]
    assert all(
        pile.graphic.variant is StockpileVariant.FIXED_PROFILE
        for pile in STOCKPILE_CHACAY_PILES
    )
    assert [(row.label, row.kpi_key) for row in STOCKPILE_CHACAY_ROWS] == [
        ('Plan', 'ton_stockpile_plan'),
        ('Capacidad', 'ton_stockpile_capacidad'),
        ('Real', 'ton_stockpile_real'),
        ('LIDAR', 'toneladas_stockpile_lidar'),
    ]


@pytest.mark.parametrize(('raw', 'expected'), [(str(i), i) for i in range(1, 9)])
def test_position_maps_eight_values_with_unloaded_and_loaded_minecarts(raw, expected):
    state = map_stockpile_chacay_store(_store({STOCKPILE_CHACAY_POSITION_KEY: _entry(raw)}))
    assert state.position.status is DisplayStatus.OK
    assert state.position.value == expected
    presentation = build_stockpile_chacay(state)
    carts = [
        node
        for node in _components(presentation)
        if getattr(node, 'className', None) in ('bi bi-minecart', 'bi bi-minecart-loaded')
    ]
    assert len(carts) == 1
    expected_icon = 'bi bi-minecart-loaded' if expected % 2 == 0 else 'bi bi-minecart'
    assert carts[0].className == expected_icon
    assert f'P{expected}' in next(
        getattr(node, 'aria-label')
        for node in _components(presentation)
        if getattr(node, 'data-kpi-inspection-key', None) == STOCKPILE_CHACAY_POSITION_KEY
    )


@pytest.mark.parametrize('raw', ['0', '9', 'P1', 'abc', '1.5', '', True])
def test_invalid_positions_do_not_display_cart(raw):
    state = map_stockpile_chacay_store(_store({STOCKPILE_CHACAY_POSITION_KEY: _entry(raw)}))
    assert state.position.status is DisplayStatus.INVALID
    content = build_stockpile_chacay(state)
    assert not any(
        getattr(node, 'className', None) in ('bi bi-minecart', 'bi bi-minecart-loaded')
        for node in _components(content)
    )


@pytest.mark.parametrize(
    ('payload', 'expected'),
    [
        (None, DisplayStatus.INVALID),
        ({'latest': None}, DisplayStatus.NOT_MAPPED),
        ({'latest': []}, DisplayStatus.INVALID),
        ({'latest': {'values': []}}, DisplayStatus.INVALID),
    ],
)
def test_unavailable_store_preserves_status_across_readings(payload, expected):
    state = map_stockpile_chacay_store(payload)
    assert state.position.status is expected
    assert all(pile.percent.status is expected for pile in state.piles)
    assert all(row.value.status is expected for row in state.rows)


def test_independent_kpi_values_and_statuses():
    state = map_stockpile_chacay_store(
        _store(
            {
                STOCKPILE_CHACAY_POSITION_KEY: _entry('8'),
                STOCKPILE_CHACAY_PILES[0].kpi_key: _entry('61,25'),
                STOCKPILE_CHACAY_PILES[1].kpi_key: {
                    'status': 'missing',
                    'value_kind': None,
                    'value': None,
                },
                STOCKPILE_CHACAY_PILES[2].kpi_key: {
                    'status': 'error',
                    'value_kind': 'value',
                    'value': None,
                },
                STOCKPILE_CHACAY_PILES[3].kpi_key: _entry('   '),
                STOCKPILE_CHACAY_ROWS[0].kpi_key: _entry('123456789,123456789'),
                STOCKPILE_CHACAY_ROWS[1].kpi_key: _entry('456'),
            }
        )
    )
    assert [pile.percent.status for pile in state.piles] == [
        DisplayStatus.OK,
        DisplayStatus.EMPTY,
        DisplayStatus.ERROR,
        DisplayStatus.INVALID,
    ]
    assert state.piles[0].percent.value == '61,25'
    assert [row.value.status for row in state.rows] == [
        DisplayStatus.OK,
        DisplayStatus.OK,
        DisplayStatus.NOT_MAPPED,
        DisplayStatus.NOT_MAPPED,
    ]
    assert state.rows[0].value.value == '123456789,123456789'
    assert state.position.value == 8


def test_all_9_visible_kpis_are_individually_inspectable():
    values = {definition.kpi_key: _entry('77') for definition in STOCKPILE_CHACAY_PILES}
    values.update(
        {definition.kpi_key: _entry('1234567890123') for definition in STOCKPILE_CHACAY_ROWS}
    )
    values[STOCKPILE_CHACAY_POSITION_KEY] = _entry('4')
    presentation = build_stockpile_chacay(map_stockpile_chacay_store(_store(values)))
    targets = [
        node
        for node in _components(presentation)
        if hasattr(node, 'data-kpi-inspection-key')
    ]
    expected = [STOCKPILE_CHACAY_POSITION_KEY] + [p.kpi_key for p in STOCKPILE_CHACAY_PILES]
    expected += [r.kpi_key for r in STOCKPILE_CHACAY_ROWS]
    assert [getattr(node, 'data-kpi-inspection-key') for node in targets] == expected
    assert all(node.role == 'button' and node.tabIndex == 0 for node in targets)
    assert [node.children for node in targets[-4:]] == ['1234567890123'] * 4


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


def test_callback_consumes_existing_plant_store_and_renders_first_card():
    dash_app = DashStub()
    register_stockpile_chacay_callback(dash_app, tool_key='integrated_operations')
    assert dash_app.args[0].component_id == dashboard_card_content_id('stockpile_chacay')
    assert dash_app.args[1].component_id == component_kpi_store_id(
        'integrated_operations', STOCKPILE_CHACAY.tool_component_key
    )
    result = dash_app.render(_store({STOCKPILE_CHACAY_POSITION_KEY: _entry('3')}))
    assert isinstance(result, Component)
    assert (
        sum(
            getattr(node, 'className', None) == 'bi bi-minecart'
            for node in _components(result)
        )
        == 1
    )
