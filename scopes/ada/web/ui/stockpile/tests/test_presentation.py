from __future__ import annotations

import base64

import pytest

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.stockpile import (
    StockpileDefinition,
    StockpileValues,
    StockpileVariant,
    build_stockpile_component,
)

VARIABLE = StockpileDefinition('pile', StockpileVariant.VARIABLE_HEIGHT, scale_max_m=28)
FIXED = StockpileDefinition('pile', StockpileVariant.FIXED_PROFILE)


def _svg(component):
    uri = component.to_plotly_json()['props']['src']
    return base64.b64decode(uri.split(',', 1)[1]).decode('utf8')


def _render(percent, height):
    return build_stockpile_component(VARIABLE, StockpileValues(percent, height))


def test_valid_source_text_is_preserved_in_svg():
    svg = _svg(_render(DisplayValue.ok('65'), DisplayValue.ok('18,2')))
    assert '65%' in svg and '18,2m' in svg


def test_no_data_in_both_uses_maximum_empty_silhouette_and_information_labels():
    svg = _svg(_render(DisplayValue.empty(), DisplayValue.not_mapped()))
    assert svg.count('Sin información') == 2
    assert 'clip-path="url(#stockpile-clip)"' not in svg
    assert 'fill="url(#stockpile-light-volume)"' not in svg
    assert 'fill="url(#stockpile-light-texture)"' not in svg


def test_missing_percentage_shows_real_height_and_no_fill():
    svg = _svg(_render(DisplayValue.empty(), DisplayValue.ok('14')))
    assert '14m' in svg and svg.count('Sin información') == 1
    assert 'clip-path="url(#stockpile-clip)"' not in svg
    assert 'fill="url(#stockpile-light-volume)"' not in svg


@pytest.mark.parametrize('missing_height', [DisplayValue.empty(), DisplayValue.not_mapped()])
def test_missing_height_preserves_percentage_label_but_not_fill(missing_height):
    svg = _svg(_render(DisplayValue.ok('65'), missing_height))
    assert '65%' in svg and svg.count('Sin información') == 1
    assert 'clip-path="url(#stockpile-clip)"' not in svg
    assert 'fill="url(#stockpile-light-volume)"' not in svg


def test_text_decimal_reading_preserves_number_and_fill():
    svg = _svg(_render(DisplayValue.ok('12,3'), DisplayValue.ok('18,2')))
    assert '12,3%' in svg
    assert '18,2m' in svg
    assert 'fill="url(#stockpile-dark-volume)"' in svg


def test_valid_zero_percentage_renders_an_empty_outline():
    svg = _svg(_render(DisplayValue.ok('0'), DisplayValue.ok('14')))
    assert '0%' in svg and '14m' in svg
    assert 'fill="url(#stockpile-light-volume)"' not in svg
    assert 'clip-path="url(#stockpile-clip)"' not in svg


def test_fixed_profile_uses_percentage_only():
    svg = _svg(build_stockpile_component(FIXED, StockpileValues(DisplayValue.ok('78'))))
    assert '78%' in svg
    assert 'Sin información' not in svg


def test_fixed_profile_missing_percentage_remains_empty():
    svg = _svg(build_stockpile_component(FIXED, StockpileValues(DisplayValue.empty())))
    assert svg.count('Sin información') == 1
    assert 'clip-path="url(#stockpile-clip)"' not in svg
    assert 'fill="url(#stockpile-light-volume)"' not in svg


@pytest.mark.parametrize(
    'value, suffix',
    [
        (DisplayValue.invalid(), 'invalid-data.svg'),
        (DisplayValue.error(), 'internal-error.svg'),
        (DisplayValue.ok('broken'), 'invalid-data.svg'),
        (DisplayValue.ok('101'), 'invalid-data.svg'),
    ],
)
def test_invalid_or_error_source_uses_system_icon(value, suffix):
    rendered = _render(value, DisplayValue.ok('14'))
    json = rendered.to_plotly_json()
    assert json['type'] == 'Span'
    assert json['props']['children'].to_plotly_json()['props']['src'].endswith(suffix)


def test_out_of_scale_height_keeps_original_text_and_caps_geometry():
    svg = _svg(_render(DisplayValue.ok('65'), DisplayValue.ok('35')))
    assert '35m' in svg
    assert '65%' in svg


def test_optional_component_identifier_absent_does_not_emit_null_id():
    rendered = build_stockpile_component(FIXED, StockpileValues(DisplayValue.ok('12')))
    assert rendered.to_plotly_json()['props'].get('id') is None
