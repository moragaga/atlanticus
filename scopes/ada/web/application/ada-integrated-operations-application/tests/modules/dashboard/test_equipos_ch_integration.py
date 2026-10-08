from __future__ import annotations

from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.equipos_ch import (
    EQUIPOS_CH_DEFINITIONS,
    build_equipos_ch,
    map_equipos_ch_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.runtime import (
    register_chancado_stmg_callback,
)
from ada.web.application.integrated_operations.modules.dashboard.module import (
    create_dashboard_module,
)
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
    return {'status': 'ok', 'value_kind': 'value', 'value': value}


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


def test_provisional_definitions_are_two_equipment_with_six_distinct_keys():
    definitions = EQUIPOS_CH_DEFINITIONS
    assert len(definitions) == 2
    keys = [key for item in definitions for key in (
        item.state_kpi_key, item.throughput_kpi_key, item.atollo_kpi_key,
    )]
    assert len(keys) == len(set(keys)) == 6


def test_callback_now_renders_three_sections_with_no_mapped_equipment_keys():
    stub = DashStub()
    register_chancado_stmg_callback(stub, tool_key='integrated_operations')
    root = stub.callback_function(_store({}))
    assert [child.className for child in root.children] == [
        'ada-io-produccion-global', 'ada-io-equipos-ch', 'ada-io-stockpile',
    ]
    targets = _targets(root.children[1])
    assert len(targets) == 6
    assert all(node.role == 'button' and node.tabIndex == 0 for node in targets)


def test_atollo_inactive_has_no_hidden_target_and_error_is_inspectable():
    a, b = EQUIPOS_CH_DEFINITIONS
    mapped = map_equipos_ch_store(_store({
        a.atollo_kpi_key: _entry(a.atollo_inactive_value),
        b.atollo_kpi_key: {'status': 'error', 'value_kind': 'value', 'value': None},
    }), EQUIPOS_CH_DEFINITIONS)
    assert mapped[0].atollo.value is False
    assert mapped[1].atollo.status is DisplayStatus.ERROR
    target_keys = [getattr(node, 'data-kpi-inspection-key') for node in
                   _targets(build_equipos_ch(mapped))]
    assert a.atollo_kpi_key not in target_keys
    assert b.atollo_kpi_key in target_keys


def test_equipment_image_assets_are_registered():
    assert ADA_EQUIPMENT_IMAGE_ASSET_LAYER in create_dashboard_module(None).asset_layers
