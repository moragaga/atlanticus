from __future__ import annotations

import pytest

from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.equipos_ch import (
    EquiposChDefinition,
    build_equipos_ch,
    map_equipos_ch_store,
)
from ada.web.ui.display_status import DisplayStatus

DEFINITIONS = (
    EquiposChDefinition(
        'one',
        'Equipo A',
        'state_a',
        'tph_a',
        'atollo_a',
        '1',
        '0',
        'rend_a',
        'minutes_a',
        'poste_a',
    ),
    EquiposChDefinition(
        'two',
        'Equipo B',
        'state_b',
        'tph_b',
        'atollo_b',
        '1',
        '0',
        'rend_b',
        'minutes_b',
        'poste_b',
    ),
)


def _value(token: str) -> dict[str, object]:
    return {
        'status': 'ok',
        'value_kind': 'value',
        'value': str(token),
        'value_type': 'text',
        'parsed_value': str(token),
    }


def _store(values: dict[str, object]) -> dict[str, object]:
    return {'latest': {'values': values}}


def _nodes(item):
    if hasattr(item, 'to_plotly_json'):
        yield item
        yield from _nodes(item.children)
    elif isinstance(item, list | tuple):
        for child in item:
            yield from _nodes(child)


def _targets(root):
    return [node for node in _nodes(root) if hasattr(node, 'data-kpi-inspection-key')]


def test_six_distinct_kpi_readings_and_states_are_isolated():
    readings = map_equipos_ch_store(
        _store(
            {
                'state_a': _value('Operando'),
                'tph_a': _value('123,4'),
                'atollo_a': _value('1'),
                'state_b': _value('error-state'),
                'tph_b': _value('90'),
                'atollo_b': _value('0'),
            }
        ),
        DEFINITIONS,
    )
    assert len(readings) == 2
    assert readings[0].state.value == 'operando'
    assert readings[0].throughput.value == '123,4'
    assert readings[0].atollo.value is True
    assert readings[1].state.status is DisplayStatus.INVALID
    assert readings[1].throughput.value == '90'
    assert readings[1].atollo.value is False


def test_atollo_inactive_is_absent_and_only_five_inspection_targets_are_rendered():
    state = map_equipos_ch_store(
        _store(
            {
                'state_a': _value('detenido'),
                'tph_a': _value('20'),
                'atollo_a': _value('1'),
                'state_b': _value('mantencion'),
                'tph_b': _value('0'),
                'atollo_b': _value('0'),
            }
        ),
        DEFINITIONS,
    )
    root = build_equipos_ch(state)
    assert {getattr(node, 'data-kpi-inspection-key') for node in _targets(root)} == {
        'state_a',
        'tph_a',
        'atollo_a',
        'state_b',
        'tph_b',
        'rend_a',
        'minutes_a',
        'poste_a',
        'rend_b',
        'minutes_b',
        'poste_b',
    }
    assert len(_targets(root)) == 11
    assert all(node.role == 'button' and node.tabIndex == 0 for node in _targets(root))


def test_atollo_degraded_status_is_visible_and_inspectable():
    for value, expected in (
        (None, DisplayStatus.NOT_MAPPED),
        (
            {
                'status': 'missing',
                'value_kind': None,
                'value': None,
                'value_type': None,
                'parsed_value': None,
            },
            DisplayStatus.EMPTY,
        ),
        (
            {
                'status': 'error',
                'value_kind': 'value',
                'value': None,
                'value_type': 'text',
                'parsed_value': None,
            },
            DisplayStatus.ERROR,
        ),
        (_value('unrecognized'), DisplayStatus.INVALID),
    ):
        values = {} if value is None else {'atollo_a': value}
        readings = map_equipos_ch_store(_store(values), DEFINITIONS)
        assert readings[0].atollo.status is expected
        assert 'atollo_a' in [
            getattr(node, 'data-kpi-inspection-key')
            for node in _targets(build_equipos_ch(readings))
        ]


def test_unavailable_store_never_implies_atollo_is_inactive():
    for store, expected in (
        ({'latest': None}, DisplayStatus.NOT_MAPPED),
        (None, DisplayStatus.INVALID),
        ({'latest': {'values': []}}, DisplayStatus.INVALID),
    ):
        readings = map_equipos_ch_store(store, DEFINITIONS)
        assert all(item.atollo.status is expected for item in readings)


def test_color_kpi_is_optional_and_absent_without_configuration():
    readings = map_equipos_ch_store(_store({'rend_a': _value('12')}), DEFINITIONS)
    assert readings[0].rendimiento_color is None
    table = build_equipos_ch(readings).children[2]
    assert 'rend_color_a' not in [
        getattr(node, 'data-kpi-inspection-key') for node in _targets(table)
    ]


def test_color_values_are_decoded_separately_with_existing_state_codes():
    colored = EquiposChDefinition(
        'one',
        'Equipo A',
        'state_a',
        'tph_a',
        'atollo_a',
        '1',
        '0',
        'rend_a',
        'minutes_a',
        'poste_a',
        rendimiento_color_kpi_key='rend_color_a',
        min_atollo_color_kpi_key='minutes_color_a',
        min_poste_color_kpi_key='poste_color_a',
    )
    readings = map_equipos_ch_store(
        _store(
            {
                'rend_a': _value('14,1'),
                'rend_color_a': _value('1'),
                'minutes_a': _value('4'),
                'minutes_color_a': _value('2'),
                'poste_a': _value('6'),
                'poste_color_a': _value('0'),
            }
        ),
        (colored, DEFINITIONS[1]),
    )
    assert readings[0].rendimiento_color.value.value == 'danger'
    assert readings[0].min_atollo_color.value.value == 'warning'
    assert readings[0].min_poste_color.value.value == 'neutral'
    assert readings[0].rendimiento.value == '14,1'
    targets = [
        getattr(node, 'data-kpi-inspection-key')
        for node in _targets(build_equipos_ch(readings).children[2])
    ]
    assert targets == [
        'rend_a',
        'rend_color_a',
        'minutes_a',
        'minutes_color_a',
        'poste_a',
        'poste_color_a',
        'rend_b',
        'minutes_b',
        'poste_b',
    ]


def test_color_failures_remain_visible_without_invalidating_values():
    colored = EquiposChDefinition(
        'one',
        'Equipo A',
        'state_a',
        'tph_a',
        'atollo_a',
        '1',
        '0',
        'rend_a',
        'minutes_a',
        'poste_a',
        rendimiento_color_kpi_key='rend_color_a',
        min_atollo_color_kpi_key='minutes_color_a',
        min_poste_color_kpi_key='poste_color_a',
    )
    readings = map_equipos_ch_store(
        _store(
            {
                'rend_a': _value('25'),
                'rend_color_a': {
                    'status': 'error',
                    'value_kind': 'value',
                    'value': None,
                    'value_type': 'text',
                    'parsed_value': None,
                },
                'minutes_a': _value('3'),
                'minutes_color_a': _value('9'),
                'poste_a': {
                    'status': 'missing',
                    'value_kind': None,
                    'value': None,
                    'value_type': None,
                    'parsed_value': None,
                },
            }
        ),
        (colored, DEFINITIONS[1]),
    )
    first = readings[0]
    assert first.rendimiento.value == '25'
    assert first.rendimiento_color.status is DisplayStatus.ERROR
    assert first.min_atollo.value == '3'
    assert first.min_atollo_color.status is DisplayStatus.INVALID
    assert first.min_poste.status is DisplayStatus.EMPTY
    assert first.min_poste_color.status is DisplayStatus.NOT_MAPPED
    table = build_equipos_ch(readings).children[2]
    targets = {getattr(node, 'data-kpi-inspection-key') for node in _targets(table)}
    assert {'rend_color_a', 'minutes_color_a', 'poste_color_a'} <= targets


def test_optional_color_key_must_be_nonempty_when_supplied_and_distinct():
    with pytest.raises(ValueError, match='non-empty'):
        EquiposChDefinition(
            'one',
            'A',
            'state',
            'tph',
            'atollo',
            '1',
            '0',
            'rend',
            'minutes',
            'poste',
            rendimiento_color_kpi_key=' ',
        )
    with pytest.raises(ValueError, match='globally distinct'):
        invalid = EquiposChDefinition(
            'other',
            'B',
            'state_b',
            'tph_b',
            'atollo_b',
            '1',
            '0',
            'rend_b',
            'minutes_b',
            'poste_b',
            min_poste_color_kpi_key='rend_a',
        )
        map_equipos_ch_store(_store({}), (DEFINITIONS[0], invalid))


def test_duplicate_keys_are_rejected():
    other = EquiposChDefinition(
        'another',
        'B',
        'state_a',
        'other_tph',
        'other_atollo',
        '1',
        '0',
        'rend_c',
        'minutes_c',
        'poste_c',
    )
    with pytest.raises(ValueError, match='globally distinct'):
        map_equipos_ch_store(_store({}), (DEFINITIONS[0], other))


def test_two_chancadores_preserve_independent_inspection_with_atollo_error():
    readings = map_equipos_ch_store(
        _store(
            {
                'state_a': _value('operando'),
                'tph_a': _value('10'),
                'atollo_a': _value('0'),
                'state_b': _value('detenido'),
                'tph_b': _value('20'),
                'atollo_b': {
                    'status': 'error',
                    'value_kind': 'value',
                    'value': None,
                    'value_type': 'text',
                    'parsed_value': None,
                },
            }
        ),
        DEFINITIONS,
    )
    root = build_equipos_ch(readings)
    targets = [getattr(node, 'data-kpi-inspection-key') for node in _targets(root)]
    assert set(targets) == {
        'state_a',
        'tph_a',
        'state_b',
        'tph_b',
        'atollo_b',
        'rend_a',
        'minutes_a',
        'poste_a',
        'rend_b',
        'minutes_b',
        'poste_b',
    }
    assert len(targets) == 11
    assert not any(
        getattr(node, 'data-kpi-inspection-key', None) == 'atollo_a' for node in _nodes(root)
    )


def test_equipment_presentation_requires_two_readings():
    state = map_equipos_ch_store(_store({}), DEFINITIONS)
    with pytest.raises(ValueError, match='exactly two'):
        build_equipos_ch(state[:1])


def test_table_metrics_remain_independent_and_preserve_source_error():
    readings = map_equipos_ch_store(
        _store(
            {
                'rend_a': _value('0,0'),
                'minutes_a': _value('0,0'),
                'poste_a': _value('197,02'),
                'rend_b': {
                    'status': 'error',
                    'value_kind': 'value',
                    'value': None,
                    'value_type': 'text',
                    'parsed_value': None,
                },
                'minutes_b': _value('0,0'),
                'poste_b': _value('-0,22'),
            }
        ),
        DEFINITIONS,
    )
    assert tuple(
        (r.rendimiento.value, r.min_atollo.value, r.min_poste.value) for r in readings
    ) == (
        ('0,0', '0,0', '197,02'),
        (None, '0,0', '-0,22'),
    )
    assert readings[1].rendimiento.status is DisplayStatus.ERROR
    assert readings[0].rendimiento.status is DisplayStatus.OK


def test_table_has_two_equipment_rows_and_six_independently_inspectable_cells():
    readings = map_equipos_ch_store(
        _store(
            {
                'rend_a': _value('10,2'),
                'minutes_a': _value('3'),
                'poste_a': _value('200'),
                'rend_b': _value('9,1'),
                'minutes_b': _value('0'),
                'poste_b': _value('-0,2'),
                'atollo_a': _value('0'),
                'atollo_b': _value('0'),
            }
        ),
        DEFINITIONS,
    )
    root = build_equipos_ch(readings)
    table = root.children[2]
    assert table.to_plotly_json()['type'] == 'Table'
    assert len(table.children[1].children) == 2
    rows = table.children[1].children
    assert [r.children[0].children for r in rows] == ['Equipo A', 'Equipo B']
    table_keys = [getattr(n, 'data-kpi-inspection-key') for n in _targets(table)]
    assert table_keys == ['rend_a', 'minutes_a', 'poste_a', 'rend_b', 'minutes_b', 'poste_b']
    assert all(n.role == 'button' and n.tabIndex == 0 for n in _targets(table))
    assert 'atollo_a' not in [getattr(n, 'data-kpi-inspection-key') for n in _targets(root)]
    assert 'atollo_b' not in [getattr(n, 'data-kpi-inspection-key') for n in _targets(root)]


def test_invalid_table_payload_does_not_hide_remaining_readings():
    readings = map_equipos_ch_store(
        _store(
            {
                'rend_a': {
                    'status': 'missing',
                    'value_kind': None,
                    'value': None,
                    'value_type': None,
                    'parsed_value': None,
                },
                'minutes_a': _value(' '),
                'poste_a': {
                    'status': 'ok',
                    'value_kind': 'json',
                    'value': {'n': 2},
                    'value_type': None,
                    'parsed_value': None,
                },
                'rend_b': _value('9'),
            }
        ),
        DEFINITIONS,
    )
    assert readings[0].rendimiento.status is DisplayStatus.EMPTY
    assert readings[0].min_atollo.status is DisplayStatus.INVALID
    assert readings[0].min_poste.status is DisplayStatus.INVALID
    assert readings[1].rendimiento.value == '9'
    assert readings[1].min_poste.status is DisplayStatus.NOT_MAPPED
