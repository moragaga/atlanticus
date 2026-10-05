from dash.development.base_component import Component

from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
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


def _point(key: str, scope: ToolScope = ToolScope.PLANT) -> AlarmBaselinePoint:
    return AlarmBaselinePoint(
        anchor_kind=AlarmBaselineAnchorKind.COMPONENT,
        anchor_key=key,
        component_key=key,
        display_name=key.title(),
        scope=scope,
    )


def _process_projection(*, with_bottom: bool) -> AlarmBaselineProjection:
    return AlarmBaselineProjection(
        tool_key='process',
        kind=ToolConfigurationKind.PROCESS,
        main_points=(
            _point('left'),
            _point('center'),
            _point('right'),
        ),
        bottom_point=_point('detail') if with_bottom else None,
    )


def _nodes(surface: Component, class_name: str) -> list[Component]:
    return [
        item
        for item in _walk(surface)
        if class_name in str(_props(item).get('className') or '').split()
    ]


def test_main_trace_uses_operational_trace_slot_center_geometry() -> None:
    surface = build_alarm_baseline_surface(_process_projection(with_bottom=False))
    traces = _nodes(surface, 'ada-alarm-baseline-surface__trace')
    points = _nodes(surface, 'ada-alarm-baseline-surface__point')

    assert len(traces) == 1
    assert _props(traces[0])['data-ada-alarm-baseline-region'] == 'main'
    assert [_props(point)['style']['--ada-alarm-baseline-point-x'] for point in points] == [
        '16.666667%',
        '50.000000%',
        '83.333333%',
    ]


def test_optional_bottom_is_a_separate_full_width_trace_with_center_anchor() -> None:
    surface = build_alarm_baseline_surface(_process_projection(with_bottom=True))
    traces = _nodes(surface, 'ada-alarm-baseline-surface__trace')
    points = _nodes(surface, 'ada-alarm-baseline-surface__point')

    assert [_props(trace)['data-ada-alarm-baseline-region'] for trace in traces] == [
        'main',
        'bottom',
    ]
    assert _props(surface)['data-ada-alarm-baseline-bottom-component-key'] == 'detail'
    assert [
        (
            _props(point)['data-ada-component-key'],
            _props(point)['data-ada-alarm-baseline-region'],
            _props(point)['style']['--ada-alarm-baseline-point-x'],
        )
        for point in points
    ] == [
        ('left', 'main', '16.666667%'),
        ('center', 'main', '50.000000%'),
        ('right', 'main', '83.333333%'),
        ('detail', 'bottom', '50.000000%'),
    ]


def test_surface_keeps_component_names_out_of_visible_content() -> None:
    surface = build_alarm_baseline_surface(_process_projection(with_bottom=True))

    assert all(
        not isinstance(getattr(item, 'children', None), str)
        for item in _walk(surface)
    )
    for point in _nodes(surface, 'ada-alarm-baseline-surface__point'):
        assert 'title' not in _props(point)


def test_surface_preserves_anchor_identity_for_future_runtime_overlay() -> None:
    surface = build_alarm_baseline_surface(_process_projection(with_bottom=True))
    points = _nodes(surface, 'ada-alarm-baseline-surface__point')

    assert _props(surface)['aria-hidden'] == 'true'
    assert _props(surface)['data-ada-alarm-baseline-tool-key'] == 'process'
    assert _props(surface)['data-ada-alarm-baseline-main-point-count'] == '3'
    assert _props(surface)['data-ada-alarm-baseline-point-count'] == '4'
    assert [_props(point)['data-ada-alarm-anchor-kind'] for point in points] == [
        'component',
        'component',
        'component',
        'component',
    ]


def test_surface_does_not_encode_runtime_alarm_state() -> None:
    surface = build_alarm_baseline_surface(_process_projection(with_bottom=True))

    for item in _walk(surface):
        props = _props(item)
        assert 'data-ada-alarm-node-state' not in props
        assert 'data-ada-alarm-severity' not in props
        assert 'data-ada-alarm-count' not in props
        assert 'data-selected' not in props
        assert 'data-previewing' not in props


def test_surface_rejects_non_projection_input() -> None:
    try:
        build_alarm_baseline_surface(object())
    except TypeError as exc:
        assert str(exc) == 'Alarm Baseline Projection is required'
    else:
        raise AssertionError('TypeError was not raised')
