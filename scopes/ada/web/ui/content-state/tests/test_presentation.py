from __future__ import annotations

import pytest
from dash import html

from ada.web.ui.content_state import ContentState, build_content_state_wrapper


def _props(component):
    return component.to_plotly_json()['props']


def _children(component):
    children = _props(component).get('children', [])
    if isinstance(children, list):
        return children
    return [children]


def test_wrapper_uses_component_key_as_only_domain_identity() -> None:
    wrapper = build_content_state_wrapper(
        component_key='global_indicators',
        children=html.Div('payload'),
    )
    props = _props(wrapper)

    assert props['data-ada-component-key'] == 'global_indicators'
    assert props['data-ada-content-state'] == 'ready'
    assert 'id' not in props
    assert 'data-ada-content-state-key' not in props


def test_wrapper_preserves_consumer_content_and_overlay_as_siblings() -> None:
    payload = html.Button('Inspect')
    wrapper = build_content_state_wrapper(
        component_key='global_indicators',
        children=payload,
        state=ContentState.STALE,
        class_name='consumer-shell',
    )
    props = _props(wrapper)
    content, overlay = _children(wrapper)

    assert props['className'] == 'ada-content-state consumer-shell'
    assert _props(content)['className'] == 'ada-content-state__content'
    assert _props(content)['children'] is payload
    assert _props(overlay)['className'] == 'ada-content-state__overlay'
    assert _props(overlay)['aria-hidden'] == 'false'


def test_ready_keeps_stable_overlay_but_marks_it_accessibility_hidden() -> None:
    wrapper = build_content_state_wrapper(
        component_key='global_indicators',
        children=html.Div('payload'),
        state=ContentState.READY,
    )
    _, overlay = _children(wrapper)

    assert _props(overlay)['aria-hidden'] == 'true'
    assert len(_children(overlay)) == 3


def test_overlay_preloads_exact_degraded_views_without_titles() -> None:
    wrapper = build_content_state_wrapper(
        component_key='global_indicators',
        children=html.Div('payload'),
        state=ContentState.SOURCE_ERROR,
    )
    _, overlay = _children(wrapper)
    views = _children(overlay)

    expected = {
        'stale': ('Información desactualizada', 'bi-cloud-slash'),
        'source_error': ('Fuente de datos con error', 'bi-exclamation-triangle-fill'),
        'construction': ('En construcción', 'bi-hammer'),
    }

    for view in views:
        view_props = _props(view)
        icon, message = _children(view)
        state = view_props['data-ada-content-state-view']
        expected_message, expected_icon = expected[state]
        assert expected_icon in _props(icon)['className']
        assert _props(message)['children'] == [expected_message]
        assert 'title' not in _props(icon)
        assert 'title' not in _props(message)


def test_wrapper_rejects_invalid_component_identity() -> None:
    with pytest.raises(ValueError, match='Invalid ADA DOM component key'):
        build_content_state_wrapper(
            component_key='Global Indicators',
            children=html.Div('payload'),
        )
