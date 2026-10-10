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
