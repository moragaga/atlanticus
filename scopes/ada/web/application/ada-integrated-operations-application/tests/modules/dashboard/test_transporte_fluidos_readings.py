from __future__ import annotations

import pytest

from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.decoder import (
    decode_transporte_fluidos_store,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.indicators import (
    FluidMetricDefinition,
    map_metrics,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.sta import (
    STA_INDICATORS,
    map_sta_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.stc import (
    STC_ESPESADOR,
    STC_INDICATORS,
    STC_LEVELS,
    map_stc_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.str.ductos import (
    DUCTOS,
    map_str_ductos_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.str.espesadores import (
    STR_ESPESADORES,
    map_str_espesadores_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.str.overview import (
    STR_TREND,
    map_str_overview_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.tranque import (
    TRANQUE_INDICATORS,
    map_tranque_readings,
)
from ada.web.ui.display_status import DisplayStatus, DisplayValue


def _entry(value: object) -> dict[str, object]:
    return {
        'status': 'ok', 'value_kind': 'value', 'value_type': 'text',
        'value': str(value), 'parsed_value': str(value),
    }


def _source(values: dict[str, object]) -> dict[str, object]:
    return {'latest': {'values': values}}


@pytest.mark.parametrize(
    ('store', 'status'),
    [
        (None, DisplayStatus.INVALID),
        ({}, DisplayStatus.NOT_MAPPED),
        ({'latest': None}, DisplayStatus.NOT_MAPPED),
        ({'latest': 3}, DisplayStatus.INVALID),
        ({'latest': {'values': None}}, DisplayStatus.INVALID),
    ],
)
def test_degraded_source_preserved_for_all_four_cards(store, status):
    readings = decode_transporte_fluidos_store(store)
    assert map_sta_readings(readings)[0].value.status is status
    assert map_tranque_readings(readings)[0].value.status is status
    stc = map_stc_readings(readings)
    assert stc.indicators[0].value.status is status
    assert stc.espesador.state.status is status
    assert stc.levels[0].level.status is status
    assert map_str_ductos_readings(readings)[0].state.status is status
    assert map_str_espesadores_readings(readings)[0].state.status is status
    assert map_str_overview_readings(readings, store).current.status is status


def test_numeric_values_and_whitespace_preserve_textual_contract():
    a, b, c = STA_INDICATORS[:3]
    readings = decode_transporte_fluidos_store(_source({
        a.kpi_key: _entry(' 15.0 '),
        b.kpi_key: _entry(0),
        c.kpi_key: _entry(12.5),
    }))
    mapped = map_sta_readings(readings)
    assert [item.value.value for item in mapped[:3]] == [' 15.0 ', '0', '12.5']


def test_independent_missing_error_invalid_and_boolean_values():
    keys = [item.kpi_key for item in STA_INDICATORS[:5]]
    values = {
        keys[1]: {'status': 'missing', 'value_kind': None, 'value_type': None,
                  'value': None, 'parsed_value': None},
        keys[2]: {'status': 'error', 'value_kind': 'json', 'value_type': None,
                  'value': None, 'parsed_value': None},
        keys[3]: _entry('true'),
        keys[4]: _entry(' '),
    }
    rows = map_sta_readings(decode_transporte_fluidos_store(_source(values)))
    assert [row.value.status for row in rows[:5]] == [
        DisplayStatus.NOT_MAPPED,
        DisplayStatus.EMPTY,
        DisplayStatus.ERROR,
        DisplayStatus.OK,
        DisplayStatus.OK,
    ]


def test_indicators_match_definitions_and_do_not_leak_source_data():
    definitions = (
        FluidMetricDefinition('First', 'first', '%'),
        FluidMetricDefinition('Second', 'second', 'kg'),
    )
    readings = {'first': DisplayValue.ok('7'), 'second': DisplayValue.ok('8')}
    result = map_metrics(readings, definitions)
    assert [item.definition for item in result] == list(definitions)
    assert [item.value.value for item in result] == ['7', '8']
    readings['first'] = DisplayValue.ok('9')
    assert result[0].value.value == '7'


def test_stc_feeding_states_and_level_color_are_preserved():
    values = {definition.kpi_key: _entry('11') for definition in STC_INDICATORS}
    values.update({
        STC_ESPESADOR.state_key: _entry('operando'),
        STC_ESPESADOR.feed_key: _entry('alimentando'),
        STC_LEVELS[0].level_key: _entry(65),
        STC_LEVELS[0].state_key: _entry('detenido'),
        STC_LEVELS[0].color_key: _entry('2'),
    })
    result = map_stc_readings(decode_transporte_fluidos_store(_source(values)))
    assert result.espesador.feed.value == 'operando'
    assert result.levels[0].level.value == '65'
    assert result.levels[0].tone == 'warning'
    assert result.levels[0].state.value == 'detenido'
    assert result.levels[1].level.status is DisplayStatus.NOT_MAPPED
    values[STC_ESPESADOR.feed_key] = _entry('other')
    values[STC_LEVELS[0].color_key] = _entry('1')
    result = map_stc_readings(decode_transporte_fluidos_store(_source(values)))
    assert result.espesador.feed.status is DisplayStatus.INVALID
    assert result.levels[0].tone == 'danger'


def test_str_equipment_states_and_history_remain_independent():
    duct = DUCTOS[0]
    tank = STR_ESPESADORES[0]
    values = {
        STR_TREND.kpi_key: _entry(' 245 '),
        duct.state_kpi_key: _entry('operando'),
        duct.solids_in_kpi_key: _entry(40),
        duct.pumps[0].state_kpi_key: {
            'status': 'error', 'value_kind': 'json', 'value_type': None,
            'value': None, 'parsed_value': None,
        },
        tank.feed_kpi_key: _entry('alimentando'),
    }
    store = _source(values)
    readings = decode_transporte_fluidos_store(store)
    duct_reading = map_str_ductos_readings(readings)[0]
    tank_reading = map_str_espesadores_readings(readings)[0]
    overview = map_str_overview_readings(readings, store)
    assert duct_reading.state.value == 'operando'
    assert duct_reading.solids_in.value == '40'
    assert duct_reading.pumps[0].state.status is DisplayStatus.ERROR
    assert tank_reading.feed.value == 'operando'
    assert overview.current.value == ' 245 '
    assert overview.history.status is DisplayStatus.NOT_MAPPED


def test_tranque_order_and_missing_values():
    a, b = TRANQUE_INDICATORS
    rows = map_tranque_readings(decode_transporte_fluidos_store(_source({b.kpi_key: _entry('17')})))
    assert [item.definition for item in rows] == [a, b]
    assert rows[0].value.status is DisplayStatus.NOT_MAPPED
    assert rows[1].value.value == '17'
