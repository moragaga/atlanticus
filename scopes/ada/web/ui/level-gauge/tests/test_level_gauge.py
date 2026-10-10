from __future__ import annotations

import pytest
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.level_gauge import LevelGaugeView, build_level_gauge


def _walk(item):
    if isinstance(item, Component):
        yield item
        yield from _walk(getattr(item, 'children', None))
    elif isinstance(item, (list, tuple)):
        for child in item:
            yield from _walk(child)


def _find_fill(root):
    return [
        node for node in _walk(root)
        if 'ada-level-gauge__fill' in getattr(node, 'className', '')
    ]


def test_round_and_square_image_selection():
    for image in ('tk', 'st'):
        view = LevelGaugeView('Tank', image, DisplayValue.ok(50), DisplayValue.ok('detenido'))
        root = build_level_gauge(view)
        urls = [node.src for node in _walk(root) if getattr(node, 'src', '').endswith('.svg')]
        assert any(url.endswith(f'/level/{image}/detenido.svg') for url in urls)


def test_state_override_is_explicit_and_does_not_depend_on_missing_source():
    view = LevelGaugeView(
        'Box', 'st', DisplayValue.ok(60), DisplayValue.not_mapped(), state_override='operando'
    )
    root = build_level_gauge(view)
    assert any(
        getattr(node, 'src', '').endswith('/level/st/operando.svg') for node in _walk(root)
    )
    without_override = LevelGaugeView('Box', 'st', DisplayValue.ok(60), DisplayValue.not_mapped())
    root = build_level_gauge(without_override)
    assert any(getattr(node, 'src', '').endswith('not-mapped.svg') for node in _walk(root))
    assert not any('/level/st/' in getattr(node, 'src', '') for node in _walk(root))


def test_level_zero_is_valid_but_missing_and_invalid_are_never_zero():
    view = LevelGaugeView('Tank', 'tk', DisplayValue.ok(0), DisplayValue.ok('operando'))
    fills = _find_fill(build_level_gauge(view))
    assert len(fills) == 1
    assert fills[0].style['height'] == '0%'
    for reading, icon in (
        (DisplayValue.empty(), 'empty-data.svg'),
        (DisplayValue.ok('garbage'), 'invalid-data.svg'),
    ):
        root = build_level_gauge(
            LevelGaugeView('Tank', 'tk', reading, DisplayValue.ok('operando'))
        )
        assert _find_fill(root) == []
        assert any(getattr(node, 'src', '').endswith(icon) for node in _walk(root))


def test_level_value_stays_within_percent_bounds():
    for value in (-2, 101, 'nan', float('inf'), True):
        view = LevelGaugeView('TK', 'tk', DisplayValue.ok(value), DisplayValue.ok('operando'))
        assert _find_fill(build_level_gauge(view)) == []


def test_fill_color_can_be_overridden_and_palette_is_whitelisted():
    view = LevelGaugeView(
        'TK', 'tk', DisplayValue.ok(50), DisplayValue.ok('operando'), fill_color='#0055AA'
    )
    assert _find_fill(build_level_gauge(view))[0].style['backgroundColor'] == '#0055AA'
    warning = LevelGaugeView(
        'TK', 'st', DisplayValue.ok(50), DisplayValue.ok('operando'), tone='warning'
    )
    assert _find_fill(build_level_gauge(warning))[0].style['backgroundColor'] == '#e0a800'
    with pytest.raises(ValueError, match='hex color'):
        LevelGaugeView(
            'TK', 'tk', DisplayValue.ok(50), DisplayValue.ok('operando'), fill_color='url(evil)'
        )
    with pytest.raises(ValueError, match='override'):
        LevelGaugeView(
            'TK', 'tk', DisplayValue.ok(50), DisplayValue.ok('operando'),
            state_override='unknown',
        )
