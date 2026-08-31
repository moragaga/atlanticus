from dash.development.base_component import Component

from ada.configuration.tools import ToolConfigurationKind, ToolScope
from ada.web.alarms.baseline_projection import (
    AlarmBaselineAnchorKind,
    AlarmBaselinePoint,
    AlarmBaselineProjection,
)
from ada.web.alarms.baseline_surface import build_alarm_baseline_surface


def _props(component: Component):
    return component.to_plotly_json()['props']


def _walk(component: Component):
    yield component
    children = getattr(component, 'children', None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if isinstance(child, Component):
            yield from _walk(child)


def _process_projection() -> AlarmBaselineProjection:
    return AlarmBaselineProjection(
        tool_key='mina',
        kind=ToolConfigurationKind.PROCESS,
        points=(
            AlarmBaselinePoint(
                anchor_kind=AlarmBaselineAnchorKind.LAYOUT_ROLE,
                anchor_key='center',
                component_key='mina',
                display_name='Mina',
                scope=ToolScope.MINE,
            ),
        ),
    )


def _integrated_operations_projection() -> AlarmBaselineProjection:
    return AlarmBaselineProjection(
        tool_key='integrated_operations',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        points=tuple(
            AlarmBaselinePoint(
                anchor_kind=AlarmBaselineAnchorKind.COMPONENT,
                anchor_key=key,
                component_key=key,
                display_name=label,
                scope=scope,
            )
            for key, label, scope in (
                ('carguio', 'Carguío', ToolScope.MINE),
                ('transporte', 'Transporte', ToolScope.MINE),
                ('molienda', 'Molienda', ToolScope.PLANT),
            )
        ),
    )


def test_process_surface_renders_one_center_point_with_real_component_identity() -> None:
    surface = build_alarm_baseline_surface(_process_projection())
    nodes = [
        item
        for item in _walk(surface)
        if _props(item).get('className') == 'ada-alarm-baseline-surface__point'
    ]

    assert _props(surface)['data-ada-alarm-baseline'] == 'process'
    assert _props(surface)['data-ada-alarm-baseline-point-count'] == '1'
    assert _props(surface)['style']['--ada-alarm-baseline-point-count'] == '1'
    assert len(nodes) == 1
    assert _props(nodes[0])['data-ada-alarm-anchor-kind'] == 'layout_role'
    assert _props(nodes[0])['data-ada-alarm-anchor-key'] == 'center'
    assert _props(nodes[0])['data-ada-component-key'] == 'mina'


def test_integrated_operations_surface_preserves_projected_component_order() -> None:
    surface = build_alarm_baseline_surface(_integrated_operations_projection())
    nodes = [
        item
        for item in _walk(surface)
        if _props(item).get('className') == 'ada-alarm-baseline-surface__point'
    ]

    assert _props(surface)['data-ada-alarm-baseline'] == 'integrated_operations'
    assert _props(surface)['data-ada-alarm-baseline-point-count'] == '3'
    assert [_props(node)['data-ada-component-key'] for node in nodes] == [
        'carguio',
        'transporte',
        'molienda',
    ]
    assert [_props(node)['data-ada-scope'] for node in nodes] == ['mine', 'mine', 'plant']


def test_surface_is_decorative_and_does_not_encode_alarm_runtime_state() -> None:
    surface = build_alarm_baseline_surface(_integrated_operations_projection())

    assert _props(surface)['aria-hidden'] == 'true'
    for item in _walk(surface):
        props = _props(item)
        assert 'data-ada-alarm-node-state' not in props
        assert 'data-ada-alarm-severity' not in props
        assert 'data-ada-alarm-count' not in props


def test_surface_rejects_non_projection_input() -> None:
    try:
        build_alarm_baseline_surface(object())
    except TypeError as exc:
        assert str(exc) == 'Alarm Baseline Projection is required'
    else:
        raise AssertionError('TypeError was not raised')
