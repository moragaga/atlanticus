from __future__ import annotations

from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.equipos_ch import (
    EQUIPOS_CH_DEFINITIONS,
    build_equipos_ch,
    map_equipos_ch_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.runtime import (
    register_chancado_stmg_callback,
)
from ada.web.application.integrated_operations.modules.dashboard.module import (
    create_dashboard_module,
)
from ada.web.kpis.readings import read_component_latest
from ada.web.ui.display_status import DisplayStatus
from ada.web.ui.equipment_image import ADA_EQUIPMENT_IMAGE_ASSET_LAYER


def _nodes(item):
    if isinstance(item, Component):
        yield item
        yield from _nodes(item.children)
    elif isinstance(item, list | tuple):
        for child in item:
            yield from _nodes(child)


def _entry(value):
    return {
        'status': 'ok',
        'value_kind': 'value',
        'value': str(value),
        'value_type': 'text',
        'parsed_value': str(value),
    }


def _store(values):
    return {'latest': {'values': values}}


def _targets(item):
    return [node for node in _nodes(item) if hasattr(node, 'data-kpi-inspection-key')]


class DashStub:
    def __init__(self):
        self.callback_function = None

    def callback(self, *_args):
        def register(fn):
            self.callback_function = fn
            return fn

        return register


def test_provisional_definitions_are_two_equipment_with_twelve_distinct_keys():
    definitions = EQUIPOS_CH_DEFINITIONS
    assert len(definitions) == 2
    keys = [
        key
        for item in definitions
        for key in (
            item.state_kpi_key,
            item.throughput_kpi_key,
            item.atollo_kpi_key,
            item.rendimiento_kpi_key,
            item.min_atollo_kpi_key,
            item.min_poste_kpi_key,
        )
    ]
    assert len(keys) == len(set(keys)) == 12


def test_callback_renders_equipment_table_before_untouched_stockpile():
    stub = DashStub()
    register_chancado_stmg_callback(stub, tool_key='integrated_operations')
    root = stub.callback_function(_store({}))
    equipos_ch = root.children[1]
    assert equipos_ch.children[2].to_plotly_json()['type'] == 'Table'
    assert len(equipos_ch.children[2].children[1].children) == 2
    assert len(_targets(equipos_ch)) == 12
    assert len(root.children[2].children[1].children) == 2
    assert all(node.role == 'button' and node.tabIndex == 0 for node in _targets(equipos_ch))


def test_atollo_inactive_has_no_hidden_target_and_error_is_inspectable():
    a, b = EQUIPOS_CH_DEFINITIONS
    mapped = map_equipos_ch_readings(
        _prepare_equipment(_store(
            {
                a.atollo_kpi_key: _entry(a.atollo_inactive_value),
                b.atollo_kpi_key: {
                    'status': 'error',
                    'value_kind': 'value',
                    'value': None,
                    'value_type': 'text',
                    'parsed_value': None,
                },
            }
        ), EQUIPOS_CH_DEFINITIONS),
        EQUIPOS_CH_DEFINITIONS,
    )
    assert mapped[0].atollo.value is False
    assert mapped[1].atollo.status is DisplayStatus.ERROR
    target_keys = [
        getattr(node, 'data-kpi-inspection-key') for node in _targets(build_equipos_ch(mapped))
    ]
    assert a.atollo_kpi_key not in target_keys
    assert b.atollo_kpi_key in target_keys


def test_equipment_image_assets_are_registered():
    assert ADA_EQUIPMENT_IMAGE_ASSET_LAYER in create_dashboard_module(None).asset_layers


def test_table_color_is_an_optional_kpi_not_a_json_payload():
    from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.equipos_ch import (
        EquiposChDefinition,
    )
    from ada.web.ui.display_status import DisplayStatus

    original = EQUIPOS_CH_DEFINITIONS[0]
    colored = EquiposChDefinition(
        original.key,
        original.label,
        original.state_kpi_key,
        original.throughput_kpi_key,
        original.atollo_kpi_key,
        original.atollo_active_value,
        original.atollo_inactive_value,
        original.rendimiento_kpi_key,
        original.min_atollo_kpi_key,
        original.min_poste_kpi_key,
        rendimiento_color_kpi_key='rendimiento_color_test',
    )
    readings = map_equipos_ch_readings(
        _prepare_equipment({
            'latest': {
                'values': {
                    original.rendimiento_kpi_key: {
                        'status': 'ok',
                        'value_kind': 'value',
                        'value': str('9,1'),
                        'value_type': 'text',
                        'parsed_value': str('9,1'),
                    },
                    'rendimiento_color_test': {
                        'status': 'ok',
                        'value_kind': 'value',
                        'value': str('2'),
                        'value_type': 'text',
                        'parsed_value': str('2'),
                    },
                }
            },
        }, (colored, EQUIPOS_CH_DEFINITIONS[1])),
        (colored, EQUIPOS_CH_DEFINITIONS[1]),
    )
    assert readings[0].rendimiento.status is DisplayStatus.OK
    assert readings[0].rendimiento_color.value.value == 'warning'
    targets = _targets(build_equipos_ch(readings))
    keys = [getattr(target, 'data-kpi-inspection-key') for target in targets]
    assert 'rendimiento_color_test' in keys
    assert original.rendimiento_kpi_key in keys


def _prepare_equipment(source, definitions):
    latest = read_component_latest(source)
    keys = (
        key
        for definition in definitions
        for key in (
        definition.state_kpi_key,
        definition.throughput_kpi_key,
        definition.atollo_kpi_key,
        definition.rendimiento_kpi_key,
        definition.min_atollo_kpi_key,
        definition.min_poste_kpi_key,
        definition.rendimiento_color_kpi_key,
        definition.min_atollo_color_kpi_key,
        definition.min_poste_color_kpi_key,
        )
        if key is not None
    )
    return {key: latest.text(key) for key in keys}
