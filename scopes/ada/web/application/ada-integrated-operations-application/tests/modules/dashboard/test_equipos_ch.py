from __future__ import annotations

import pytest

from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.equipos_ch import (
    EquiposChDefinition,
    build_equipos_ch,
    map_equipos_ch_store,
)
from ada.web.ui.display_status import DisplayStatus


DEFINITIONS = (
    EquiposChDefinition('one', 'Equipo A', 'state_a', 'tph_a', 'atollo_a', '1', '0'),
    EquiposChDefinition('two', 'Equipo B', 'state_b', 'tph_b', 'atollo_b', '1', '0'),
)


def _value(token: str) -> dict[str, object]:
    return {'status': 'ok', 'value_kind': 'value', 'value': token}


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
    readings = map_equipos_ch_store(_store({
        'state_a': _value('Operando'), 'tph_a': _value('123,4'), 'atollo_a': _value('1'),
        'state_b': _value('error-state'), 'tph_b': _value('90'), 'atollo_b': _value('0'),
    }), DEFINITIONS)
    assert len(readings) == 2
    assert readings[0].state.value == 'operando'
    assert readings[0].throughput.value == '123,4'
    assert readings[0].atollo.value is True
    assert readings[1].state.status is DisplayStatus.INVALID
    assert readings[1].throughput.value == '90'
    assert readings[1].atollo.value is False


def test_atollo_inactive_is_absent_and_only_five_inspection_targets_are_rendered():
    state = map_equipos_ch_store(_store({
        'state_a': _value('detenido'), 'tph_a': _value('20'), 'atollo_a': _value('1'),
        'state_b': _value('mantencion'), 'tph_b': _value('0'), 'atollo_b': _value('0'),
    }), DEFINITIONS)
    root = build_equipos_ch(state)
    assert [getattr(node, 'data-kpi-inspection-key') for node in _targets(root)] == [
        'state_a', 'tph_a', 'atollo_a', 'state_b', 'tph_b',
    ]
    assert all(node.role == 'button' and node.tabIndex == 0 for node in _targets(root))


def test_atollo_degraded_status_is_visible_and_inspectable():
    for value, expected in (
        (None, DisplayStatus.NOT_MAPPED),
        ({'status': 'missing', 'value_kind': None, 'value': None}, DisplayStatus.EMPTY),
        ({'status': 'error', 'value_kind': 'value', 'value': None}, DisplayStatus.ERROR),
        (_value('unrecognized'), DisplayStatus.INVALID),
    ):
        values = {} if value is None else {'atollo_a': value}
        readings = map_equipos_ch_store(_store(values), DEFINITIONS)
        assert readings[0].atollo.status is expected
        assert 'atollo_a' in [getattr(node, 'data-kpi-inspection-key')
                              for node in _targets(build_equipos_ch(readings))]


def test_unavailable_store_never_implies_atollo_is_inactive():
    for store, expected in (
        ({'latest': None}, DisplayStatus.NOT_MAPPED),
        (None, DisplayStatus.INVALID),
        ({'latest': {'values': []}}, DisplayStatus.INVALID),
    ):
        readings = map_equipos_ch_store(store, DEFINITIONS)
        assert all(item.atollo.status is expected for item in readings)


def test_duplicate_keys_are_rejected():
    other = EquiposChDefinition('another', 'B', 'state_a', 'other_tph', 'other_atollo', '1', '0')
    with pytest.raises(ValueError, match='globally distinct'):
        map_equipos_ch_store(_store({}), (DEFINITIONS[0], other))
