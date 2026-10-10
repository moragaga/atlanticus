from __future__ import annotations

from decimal import Decimal

import pytest
from dash import html
from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay import (
    build_stockpile_chacay,
    decode_stockpile_chacay_store,
    map_stockpile_chacay_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay.feeders import (
    STOCKPILE_CHACAY_FEEDER_GROUPS,
    ChacayFeederDefinition,
    build_chacay_feeders,
    map_chacay_feeders_readings,
)
from ada.web.ui.display_status import DisplayStatus, resolve_status_visual
from ada.web.ui.feeder import FeederColor


def _map_stockpile(store):
    readings, _ = decode_stockpile_chacay_store(store)
    return map_stockpile_chacay_readings(readings)


def _map_feeders(store, definitions=STOCKPILE_CHACAY_FEEDER_GROUPS):
    readings, _ = decode_stockpile_chacay_store(store, feeder_definitions=definitions)
    return map_chacay_feeders_readings(readings, definitions)


def _store(values: dict[str, object]) -> dict[str, object]:
    return {'latest': {'values': values}}


def _ok(value: object) -> dict[str, object]:
    return {
        'status': 'ok',
        'value_kind': 'value',
        'value': str(value),
        'value_type': 'text',
        'parsed_value': str(value),
    }


def _walk(item):
    if isinstance(item, Component):
        yield item
        yield from _walk(item.children)
    elif isinstance(item, list | tuple):
        for child in item:
            yield from _walk(child)


def test_existing_four_lines_preserve_all_sixteen_reference_keys():
    keys = [item.value_kpi_key for group in STOCKPILE_CHACAY_FEEDER_GROUPS for item in group]
    assert keys == [
        *(f'velocidad_feeder{x:03d}_linea1_real' for x in range(15, 19)),
        *(f'velocidad_feeder{x:03d}_linea2_real' for x in range(19, 23)),
        *(f'velocidad_feeder{x:03d}_linea3_real' for x in range(701, 705)),
        *(f'velocidad_feeder{x:04d}_linea4_real' for x in range(5001, 5005)),
    ]
    assert len(keys) == len(set(keys)) == 16


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('0', Decimal('0')),
        ('19.75', Decimal('19.75')),
        ('19,75', Decimal('19.75')),
        (25, Decimal('25')),
        (125.5, Decimal('125.5')),
    ],
)
def test_numeric_values_are_preserved_and_zero_is_valid(raw, expected):
    key = STOCKPILE_CHACAY_FEEDER_GROUPS[0][0].value_kpi_key
    result = _map_feeders(_store({key: _ok(raw)}))
    assert result[0][0].value.status is DisplayStatus.OK
    assert result[0][0].value.value == expected


@pytest.mark.parametrize('raw', [True, -1, 'abc', '', 'NaN', 'Infinity'])
def test_invalid_numeric_readings_do_not_become_zero(raw):
    key = STOCKPILE_CHACAY_FEEDER_GROUPS[0][0].value_kpi_key
    result = _map_feeders(_store({key: _ok(raw)}))
    assert result[0][0].value.status is DisplayStatus.INVALID


def test_each_feeder_preserves_its_own_degraded_state():
    keys = [item.value_kpi_key for group in STOCKPILE_CHACAY_FEEDER_GROUPS for item in group]
    values = {
        keys[0]: _ok('35.5'),
        keys[1]: {
            'status': 'missing',
            'value_kind': None,
            'value': None,
            'value_type': None,
            'parsed_value': None,
        },
        keys[2]: {
            'status': 'error',
            'value_kind': 'value',
            'value': None,
            'value_type': 'text',
            'parsed_value': None,
        },
        keys[3]: _ok(''),
    }
    groups = _map_feeders(_store(values))
    statuses = [item.value.status for group in groups for item in group]
    assert statuses == [
        DisplayStatus.OK,
        DisplayStatus.EMPTY,
        DisplayStatus.ERROR,
        DisplayStatus.INVALID,
        *[DisplayStatus.NOT_MAPPED] * 12,
    ]


@pytest.mark.parametrize(
    ('source', 'status'),
    [
        (None, DisplayStatus.INVALID),
        ({'latest': None}, DisplayStatus.NOT_MAPPED),
        ({'latest': {'values': []}}, DisplayStatus.INVALID),
    ],
)
def test_unavailable_store_propagates_shared_status(source, status):
    groups = _map_feeders(source)
    assert all(reading.value.status is status for group in groups for reading in group)


def test_optional_color_is_separate_from_numeric_value():
    key = STOCKPILE_CHACAY_FEEDER_GROUPS[0][0].value_kpi_key
    definitions = ((ChacayFeederDefinition(key, color_kpi_key='feeder_color_example'),),)
    result = _map_feeders(
        _store({key: _ok('15.25'), 'feeder_color_example': _ok('2')}),
        definitions,
    )
    assert result[0][0].value.value == Decimal('15.25')
    assert result[0][0].color is FeederColor.WARNING
    other = _map_feeders(_store({key: _ok('15.25')}), definitions)
    assert other[0][0].color is None


def test_sixteen_feeder_kpis_remain_inspectable_in_the_card():
    keys = [item.value_kpi_key for group in STOCKPILE_CHACAY_FEEDER_GROUPS for item in group]
    values = {key: _ok(str(index * 6)) for index, key in enumerate(keys)}
    root = build_stockpile_chacay(_map_stockpile(_store(values)))
    targets = [
        item for item in _walk(root) if getattr(item, 'data-kpi-inspection-key', None) is not None
    ]
    inspection_keys = [getattr(item, 'data-kpi-inspection-key') for item in targets]
    assert all(inspection_keys.count(key) == 1 for key in keys)
    assert all(item.role == 'button' and item.tabIndex == 0 for item in targets)


def test_degraded_feeders_use_the_shared_status_icons():
    content = build_chacay_feeders(_map_feeders(_store({})))
    icons = [node for node in _walk(content) if isinstance(node, html.Img)]
    assert len(icons) == 16
    assert all(icon.alt == resolve_status_visual(DisplayStatus.NOT_MAPPED).alt for icon in icons)
