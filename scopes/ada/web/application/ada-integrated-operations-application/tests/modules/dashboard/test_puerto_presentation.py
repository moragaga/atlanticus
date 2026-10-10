from __future__ import annotations

from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.plant.puerto.decoder import (
    decode_puerto_store,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.puerto.desaladora import (
    build_desaladora,
    map_desaladora_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.puerto.puerto import (
    FILTERS,
    TANKS,
    build_puerto,
    map_puerto_readings,
)
from ada.web.ui.display_status import DisplayStatus
from ada.web.ui.equipment_image import ADA_EQUIPMENT_IMAGE_ASSET_LAYER


def _walk(item):
    if isinstance(item, Component):
        yield item
        yield from _walk(getattr(item, 'children', None))
    elif isinstance(item, (list, tuple)):
        for child in item:
            yield from _walk(child)


def test_render_structure_with_two_filter_rows_and_four_tanks():
    readings, histories = decode_puerto_store({'latest': {'values': {}}})
    root = build_puerto(map_puerto_readings(readings, histories))
    assert isinstance(root, Component)
    filters = [node for node in _walk(root) if (getattr(node, 'className', '') or '') == 'ada-io-puerto__filter']
    assert len(filters) == len(FILTERS) == 8
    tanks = [node for node in _walk(root) if (getattr(node, 'className', '') or '') == 'ada-level-gauge']
    assert len(tanks) == len(TANKS) == 4
    keys = [getattr(node, 'data-kpi-inspection-key') for node in _walk(root) if getattr(node, 'data-kpi-inspection-key', None)]
    assert len(keys) == len(set(keys))
    assert set(x.state_key for x in FILTERS).issubset(keys)
    assert set(x.level_key for x in TANKS).issubset(keys)


def test_desaladora_stays_renderable_on_missing_data():
    readings, histories = decode_puerto_store({'latest': {'values': {}}})
    model = map_desaladora_readings(readings, histories)
    assert model.trend_history.status is DisplayStatus.NOT_MAPPED
    assert isinstance(build_desaladora(model), Component)


def test_puerto_uses_shared_equipment_images_for_filter_and_shipment():
    source = {
        'latest': {
            'values': {
                'fl_001_estado_inst': {
                    'status': 'ok', 'value_kind': 'value', 'value_type': 'text',
                    'value': 'Operando', 'parsed_value': 'Operando',
                },
                'embarque_estado_inst': {
                    'status': 'ok', 'value_kind': 'value', 'value_type': 'text',
                    'value': 'Detenido', 'parsed_value': 'Detenido',
                },
            }
        }
    }
    readings, histories = decode_puerto_store(source)
    root = build_puerto(map_puerto_readings(readings, histories))
    srcs = [node.src for node in _walk(root) if getattr(node, 'src', None)]
    prefix = f'/assets/{ADA_EQUIPMENT_IMAGE_ASSET_LAYER.target_name}/img/equipment/'
    assert prefix + 'filtro/operando.svg' in srcs
    assert prefix + 'barco/detenido.svg' in srcs
    assert any(item.endswith('/img/status/not-mapped.svg') for item in srcs)
    assert not any('/img/puerto/' in item for item in srcs)
