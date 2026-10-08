from __future__ import annotations

import base64

import pytest

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.stockpile import StockpileItem, StockpilePanel, build_stockpile_panel


def _props(component):
    if hasattr(component, 'to_plotly_json'):
        props = component.to_plotly_json()['props']
        yield props
        yield from _props(props.get('children'))
    elif isinstance(component, (list, tuple)):
        for child in component:
            yield from _props(child)


def _text(component):
    if hasattr(component, 'to_plotly_json'):
        yield from _text(component.to_plotly_json()['props'].get('children'))
    elif isinstance(component, (list, tuple)):
        for child in component:
            yield from _text(child)
    elif isinstance(component, str):
        yield component


def _sources(component) -> list[str]:
    return [value['src'] for value in _props(component) if isinstance(value.get('src'), str)]


def _panel(
    percentage: DisplayValue | None = None,
    height: DisplayValue | None = None,
) -> StockpilePanel:
    if percentage is None:
        percentage = DisplayValue.ok('65')
    if height is None:
        height = DisplayValue.ok('18,2')
    return StockpilePanel(
        items=(
            StockpileItem(key='pile_a', label='Pila A', percentage=percentage, height_m=height),
        ),
        scale_max_m=28,
    )


def test_valid_text_values_render_unchanged_without_kpi_keys():
    component = build_stockpile_panel(_panel())
    text = tuple(_text(component))
    assert 'Pila A' in text
    assert '65' in text
    assert '18,2' in text
    assert '%' in text
    assert 'm' in text
    generated = [
        source for source in _sources(component) if source.startswith('data:image/svg+xml;base64,')
    ]
    assert len(generated) == 1


def test_multiple_piles_keep_distinct_shapes_and_values():
    model = StockpilePanel(
        items=(
            StockpileItem('pile_a', 'A', DisplayValue.ok('20'), DisplayValue.ok('8')),
            StockpileItem('pile_b', 'B', DisplayValue.ok('90'), DisplayValue.ok('23')),
        ),
        scale_max_m=30,
    )
    component = build_stockpile_panel(model)
    shapes = [
        source for source in _sources(component) if source.startswith('data:image/svg+xml;base64,')
    ]
    assert len(shapes) == 2
    first_svg = base64.b64decode(shapes[0].split(',')[1])
    second_svg = base64.b64decode(shapes[1].split(',')[1])
    assert first_svg != second_svg
    assert {'A', 'B', '20', '90', '8', '23'}.issubset(set(_text(component)))


@pytest.mark.parametrize(
    ('display', 'expected_icon'),
    [
        (DisplayValue.not_mapped(), 'not-mapped.svg'),
        (DisplayValue.empty(), 'empty-data.svg'),
        (DisplayValue.invalid(), 'invalid-data.svg'),
        (DisplayValue.error(), 'internal-error.svg'),
        (DisplayValue.ok('n/a'), 'invalid-data.svg'),
    ],
)
def test_height_failure_uses_system_icon_and_keeps_percentage(display, expected_icon):
    component = build_stockpile_panel(_panel(height=display))
    assert any(source.endswith('/img/status/' + expected_icon) for source in _sources(component))
    assert not any(
        source.startswith('data:image/svg+xml;base64,') for source in _sources(component)
    )
    assert '65' in tuple(_text(component))
    assert '18,2' not in tuple(_text(component))


@pytest.mark.parametrize(
    ('display', 'expected_icon'),
    [
        (DisplayValue.not_mapped(), 'not-mapped.svg'),
        (DisplayValue.empty(), 'empty-data.svg'),
        (DisplayValue.invalid(), 'invalid-data.svg'),
        (DisplayValue.error(), 'internal-error.svg'),
        (DisplayValue.ok('150'), 'invalid-data.svg'),
    ],
)
def test_percentage_failure_keeps_valid_height_and_geometry(display, expected_icon):
    component = build_stockpile_panel(_panel(percentage=display))
    assert any(source.endswith('/img/status/' + expected_icon) for source in _sources(component))
    assert any(source.startswith('data:image/svg+xml;base64,') for source in _sources(component))
    assert '18,2' in tuple(_text(component))


def test_out_of_scale_height_preserves_readout_without_inventing_maximum():
    component = build_stockpile_panel(_panel(height=DisplayValue.ok('35')))
    assert '35' in tuple(_text(component))
    assert '28' not in tuple(_text(component))


def test_invalid_panel_is_rejected():
    with pytest.raises(TypeError, match='StockpilePanel'):
        build_stockpile_panel(object())
