from __future__ import annotations

import pytest

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.stockpile import StockpileItem, StockpilePanel, build_stockpile_panel


def _item(**colors):
    return StockpileItem(
        key='pile_1',
        label='Pila 1',
        percentage=DisplayValue.ok('65'),
        height_m=DisplayValue.ok('18'),
        **colors,
    )


def _properties(component):
    if hasattr(component, 'to_plotly_json'):
        props = component.to_plotly_json()['props']
        yield props
        yield from _properties(props.get('children'))
    elif isinstance(component, (list, tuple)):
        for child in component:
            yield from _properties(child)


def _text(component):
    if hasattr(component, 'to_plotly_json'):
        yield from _text(component.to_plotly_json()['props'].get('children'))
    elif isinstance(component, (list, tuple)):
        for child in component:
            yield from _text(child)
    elif isinstance(component, str):
        yield component


def _graphics(component):
    return [
        props['src']
        for props in _properties(component)
        if isinstance(props.get('src'), str) and props['src'].startswith('data:image/svg+xml;base64,')
    ]


def test_percentage_does_not_change_stockpile_geometry():
    first = StockpilePanel(items=(_item(),), scale_max_m=28)
    second = StockpilePanel(
        items=(StockpileItem('pile_1', 'Pila 1', DisplayValue.ok('85'), DisplayValue.ok('18')),),
        scale_max_m=28,
    )
    first_view = build_stockpile_panel(first)
    second_view = build_stockpile_panel(second)

    assert _graphics(first_view) == _graphics(second_view)
    assert {'65', '%', '18', 'm'}.issubset(set(_text(first_view)))
    assert {'85', '%', '18', 'm'}.issubset(set(_text(second_view)))


def test_per_item_colors_are_applied_independently():
    panel = StockpilePanel(
        items=(
            _item(percentage_background_color='#123456', percentage_text_color='#FFFFFF'),
            StockpileItem('pile_2', 'Pila 2', DisplayValue.ok('30'), DisplayValue.ok('5')),
        ),
        scale_max_m=28,
    )
    styles = [props['style'] for props in _properties(build_stockpile_panel(panel)) if 'style' in props]

    assert styles == [
        {
            '--ada-stockpile-percentage-background': '#123456',
            '--ada-stockpile-percentage-text': '#FFFFFF',
        }
    ]


@pytest.mark.parametrize('color', ['', '#12', '#12345G', 'red', 'url(example)', 42, True])
def test_invalid_hex_color_is_rejected(color):
    with pytest.raises(ValueError, match='hex color'):
        _item(percentage_background_color=color)


def test_percentage_failure_preserves_valid_height_and_configured_color():
    item = StockpileItem(
        key='pile_1',
        label='Pila 1',
        percentage=DisplayValue.invalid(),
        height_m=DisplayValue.ok('18'),
        percentage_background_color='#123456',
    )
    view = build_stockpile_panel(StockpilePanel(items=(item,), scale_max_m=28))

    assert {'18', 'm'}.issubset(set(_text(view)))
    assert '65' not in set(_text(view))
    assert len(_graphics(view)) == 1
    assert any(
        props.get('style') == {'--ada-stockpile-percentage-background': '#123456'}
        for props in _properties(view)
    )
