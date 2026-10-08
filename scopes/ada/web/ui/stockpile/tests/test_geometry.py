from __future__ import annotations

import base64
from xml.etree import ElementTree

from ada.web.ui.stockpile import StockpileDefinition, StockpileVariant
from ada.web.ui.stockpile.svg import (
    StockpileRenderValues,
    build_stockpile_data_uri,
    build_stockpile_svg,
)


def _values(*, height_ratio: float = 1.0, percent: float = 65.0) -> StockpileRenderValues:
    return StockpileRenderValues(
        percent=percent, height_ratio=height_ratio, percent_text='65%', height_text='18,2m'
    )


def test_variable_height_changes_geometry_at_different_heights():
    definition = StockpileDefinition('pile', StockpileVariant.VARIABLE_HEIGHT, scale_max_m=28)
    low = build_stockpile_svg(definition, _values(height_ratio=0.2))
    high = build_stockpile_svg(definition, _values(height_ratio=0.8))
    assert low != high
    for svg in (low, high):
        assert ElementTree.fromstring(svg).tag.endswith('svg')


def test_fixed_profile_supports_one_pile_and_data_uri():
    definition = StockpileDefinition('pile', StockpileVariant.FIXED_PROFILE)
    uri = build_stockpile_data_uri(definition, _values())
    assert uri.startswith('data:image/svg+xml;base64,')
    svg = base64.b64decode(uri.split(',', 1)[1]).decode('utf8')
    assert ElementTree.fromstring(svg).tag.endswith('svg')
    assert '65%' in svg


def test_zero_fill_does_not_draw_dark_material():
    definition = StockpileDefinition('pile', StockpileVariant.FIXED_PROFILE)
    svg = build_stockpile_svg(definition, _values(percent=0))
    assert 'clip-path="url(#stockpile-clip)"' not in svg
