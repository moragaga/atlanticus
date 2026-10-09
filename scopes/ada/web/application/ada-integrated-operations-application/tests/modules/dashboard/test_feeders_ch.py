from __future__ import annotations

import pytest

from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.equipos_ch import (
    FEEDERS_CH_DEFINITIONS,
    FeederKpiDefinition,
    map_feeders_store,
)
from ada.web.ui.display_status import DisplayStatus
from ada.web.ui.feeder import FeederColor


def _store(values: dict[str, object]) -> dict[str, object]:
    return {'latest': {'values': values}}


def _entry(value: object, *, kind: str = 'value') -> dict[str, object]:
    return {'status': 'ok', 'value_kind': kind, 'value': value}


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [('0', 0), ('75', 75), ('100', 100), ('112', 112), (' 09 ', 9)],
)
def test_collector_integer_text_is_converted_without_losing_the_real_percentage(raw, expected):
    definition = FEEDERS_CH_DEFINITIONS[0]
    reading = map_feeders_store(
        _store({definition.percent_kpi_key: _entry(raw)}), (definition,)
    )[0]
    assert reading.percent.status is DisplayStatus.OK
    assert type(reading.percent.value) is int
    assert reading.percent.value == expected


@pytest.mark.parametrize('raw', ['12.0', '12,5', '-3', 'x', '', '1e2', '12%'])
def test_non_integer_or_negative_text_is_invalid(raw):
    definition = FEEDERS_CH_DEFINITIONS[0]
    reading = map_feeders_store(
        _store({definition.percent_kpi_key: _entry(raw)}), (definition,)
    )[0]
    assert reading.percent.status is DisplayStatus.INVALID


@pytest.mark.parametrize('raw', [2.0, True, None])
def test_floats_booleans_and_null_are_invalid(raw):
    definition = FEEDERS_CH_DEFINITIONS[0]
    reading = map_feeders_store(
        _store({definition.percent_kpi_key: _entry(raw)}), (definition,)
    )[0]
    assert reading.percent.status is DisplayStatus.INVALID


def test_native_integer_is_accepted_without_float_conversion():
    definition = FEEDERS_CH_DEFINITIONS[0]
    reading = map_feeders_store(
        _store({definition.percent_kpi_key: _entry(113)}), (definition,)
    )[0]
    assert reading.percent.status is DisplayStatus.OK
    assert type(reading.percent.value) is int
    assert reading.percent.value == 113


def test_four_feeder_statuses_are_independent():
    a, b, c, d = FEEDERS_CH_DEFINITIONS
    readings = map_feeders_store(
        _store({
            a.percent_kpi_key: _entry('100'),
            b.percent_kpi_key: {'status': 'missing', 'value_kind': None, 'value': None},
            c.percent_kpi_key: _entry('112'),
            d.percent_kpi_key: {'status': 'error', 'value_kind': 'value', 'value': None},
        }),
        FEEDERS_CH_DEFINITIONS,
    )
    assert [item.percent.status for item in readings] == [
        DisplayStatus.OK,
        DisplayStatus.EMPTY,
        DisplayStatus.OK,
        DisplayStatus.ERROR,
    ]
    assert readings[0].percent.value == 100
    assert readings[2].percent.value == 112


def test_optional_color_does_not_degrade_the_valid_percentage():
    definition = FeederKpiDefinition('x', 'X', 'percent_x', 'color_x')
    sources = (
        ({}, DisplayStatus.NOT_MAPPED),
        ({'color_x': {'status': 'error', 'value_kind': 'value', 'value': None}}, DisplayStatus.ERROR),
        ({'color_x': _entry('5')}, DisplayStatus.INVALID),
    )
    for values, expected in sources:
        reading = map_feeders_store(
            _store({'percent_x': _entry('105'), **values}), (definition,)
        )[0]
        assert reading.percent.status is DisplayStatus.OK
        assert reading.percent.value == 105
        assert reading.color.status is expected


def test_unconfigured_color_produces_no_color_reading():
    definition = FEEDERS_CH_DEFINITIONS[0]
    reading = map_feeders_store(
        _store({definition.percent_kpi_key: _entry('82')}), (definition,)
    )[0]
    assert reading.percent.value == 82
    assert reading.color is None


@pytest.mark.parametrize(
    ('code', 'color'),
    [('0', FeederColor.NEUTRAL), ('1', FeederColor.DANGER), ('2', FeederColor.WARNING)],
)
def test_color_codes_are_decoded_independently(code, color):
    definition = FeederKpiDefinition('x', 'X', 'percent_x', 'color_x')
    reading = map_feeders_store(
        _store({'percent_x': _entry('82'), 'color_x': _entry(code)}), (definition,)
    )[0]
    assert reading.percent.value == 82
    assert reading.color.value is color


def test_invalid_payload_or_latest_source_reports_its_status():
    definition = FEEDERS_CH_DEFINITIONS[0]
    key = definition.percent_kpi_key
    cases = (
        (_store({key: _entry({'value': 80}, kind='json')}), DisplayStatus.INVALID),
        (None, DisplayStatus.INVALID),
        ({'latest': None}, DisplayStatus.NOT_MAPPED),
        ({'latest': {'values': []}}, DisplayStatus.INVALID),
    )
    for store, expected in cases:
        reading = map_feeders_store(store, (definition,))[0]
        assert reading.percent.status is expected


def test_duplicate_kpi_keys_are_rejected():
    first = FeederKpiDefinition('a', 'A', 'percent_a')
    second = FeederKpiDefinition('b', 'B', 'percent_a')
    with pytest.raises(ValueError, match='globally distinct'):
        map_feeders_store(_store({}), (first, second))
