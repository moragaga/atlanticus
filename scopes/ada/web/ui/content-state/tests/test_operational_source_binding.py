from dash import html

from ada.web.content_state import ContentState
from ada.web.ui.content_state import build_content_state_wrapper


def _props(node):
    return node.to_plotly_json()['props']


def test_operational_wrapper_declares_selected_sources_without_tool_key():
    wrapper = build_content_state_wrapper(
        component_key=None,
        children=html.Div('payload'),
        operational_runtime=True,
        source_keys=('pi', 'dispatch'),
    )
    props = _props(wrapper)
    assert props['data-ada-content-state-operational'] == 'true'
    assert props['data-ada-content-state-sources'] == 'pi,dispatch'
    assert 'data-ada-content-state-tool-key' not in props


def test_operational_wrapper_distinguishes_independence_from_unclassified():
    independent = build_content_state_wrapper(
        component_key=None,
        children=html.Div('payload'),
        operational_runtime=True,
        source_keys=(),
    )
    unclassified = build_content_state_wrapper(
        component_key=None,
        children=html.Div('payload'),
        operational_runtime=True,
    )
    assert _props(independent)['data-ada-content-state-sources'] == ''
    assert 'data-ada-content-state-sources' not in _props(unclassified)


def test_declared_construction_preserves_priority_with_explicit_sources():
    wrapper = build_content_state_wrapper(
        component_key=None,
        children=html.Div('payload'),
        state=ContentState.CONSTRUCTION,
        runtime_state=ContentState.SOURCE_ERROR,
        operational_runtime=True,
        source_keys=('dispatch',),
    )
    assert _props(wrapper)['data-ada-content-state'] == 'construction'
