from __future__ import annotations

import base64
from xml.etree import ElementTree

from ada.web.ui.stockpile.geometry import (
    closed_profile_path,
    interpolate_profile,
    scaled_profile,
)
from ada.web.ui.stockpile.svg import build_stockpile_data_uri, build_stockpile_svg


def _svg_text(data_uri: str) -> str:
    prefix = 'data:image/svg+xml;base64,'
    assert data_uri.startswith(prefix)
    encoded = data_uri[len(prefix) :]
    return base64.b64decode(encoded).decode('utf-8')


def test_svg_shape_changes_with_height_under_same_scale():
    small = build_stockpile_svg(8, scale_max_m=30)
    medium = build_stockpile_svg(16, scale_max_m=30)
    large = build_stockpile_svg(23, scale_max_m=30)
    assert small != medium != large
    assert len({small, medium, large}) == 3
    for svg in (small, medium, large):
        assert ElementTree.fromstring(svg).tag.endswith('svg')


def test_visual_scale_is_explicit_and_overflow_caps_geometry_only():
    at_limit = build_stockpile_svg(28, scale_max_m=28)
    over_limit = build_stockpile_svg(60, scale_max_m=28)
    common_scale = build_stockpile_svg(14, scale_max_m=28)
    larger_scale = build_stockpile_svg(14, scale_max_m=30)
    assert at_limit == over_limit
    assert common_scale != larger_scale


def test_svg_data_uri_contains_only_generated_geometry():
    svg = _svg_text(build_stockpile_data_uri(15, scale_max_m=30))
    assert '<svg' in svg
    assert '<path' in svg
    assert '15 m' not in svg


def test_zero_height_is_a_defined_geometry_not_an_error():
    path = closed_profile_path(scaled_profile(interpolate_profile(0)))
    assert path.startswith('M ')
    assert path.endswith('Z')
