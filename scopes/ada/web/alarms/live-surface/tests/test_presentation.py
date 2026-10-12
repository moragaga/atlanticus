from dash.development.base_component import Component

from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
from ada.web.alarms.baseline_projection import (
    AlarmBaselineAnchorKind, AlarmBaselinePoint, AlarmBaselineProjection,
)
from ada.web.alarms.live_surface import build_alarm_live_surface


def _walk(node: Component):
    yield node
    children = getattr(node, 'children', None)
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if isinstance(child, Component):
            yield from _walk(child)


def test_live_surface_keeps_static_baseline_and_accessible_board():
    projection = AlarmBaselineProjection(
        tool_key='io', kind=ToolConfigurationKind.PROCESS,
        main_points=(AlarmBaselinePoint(
            anchor_kind=AlarmBaselineAnchorKind.COMPONENT, anchor_key='crusher',
            component_key='crusher', display_name='Crusher', scope=ToolScope.PLANT,
        ),),
    )
    surface = build_alarm_live_surface(projection)
    props = [node.to_plotly_json()['props'] for node in _walk(surface)]
    assert props[0]['data-ada-alarm-live-tool-key'] == 'io'
    assert any(item.get('id') == 'ada-alarm-live-board' for item in props)
    assert any(item.get('aria-hidden') == 'true' and item.get('data-ada-alarm-baseline') for item in props)
    assert any(item.get('data-ada-component-key') == 'crusher' for item in props)
