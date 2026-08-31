from __future__ import annotations

from dash import html

from ada.web.alarms.baseline_projection import AlarmBaselinePoint, AlarmBaselineProjection


def build_alarm_baseline_surface(projection: AlarmBaselineProjection) -> html.Div:
    if not isinstance(projection, AlarmBaselineProjection):
        raise TypeError('Alarm Baseline Projection is required')
    kind_class = projection.kind.value.replace('_', '-')
    return html.Div(
        [
            html.Div(className='ada-alarm-baseline-surface__line'),
            html.Div(
                [_build_point(point, index=index) for index, point in enumerate(projection.points)],
                className='ada-alarm-baseline-surface__points',
            ),
        ],
        className=(f'ada-alarm-baseline-surface ada-alarm-baseline-surface--{kind_class}'),
        style={'--ada-alarm-baseline-point-count': str(len(projection.points))},
        **{
            'aria-hidden': 'true',
            'data-ada-alarm-baseline': projection.kind.value,
            'data-ada-alarm-baseline-tool-key': projection.tool_key,
            'data-ada-alarm-baseline-point-count': str(len(projection.points)),
        },
    )


def _build_point(point: AlarmBaselinePoint, *, index: int) -> html.Span:
    return html.Span(
        html.Span(className='ada-alarm-baseline-surface__point-dot'),
        className='ada-alarm-baseline-surface__point',
        title=point.display_name,
        **{
            'data-ada-alarm-baseline-index': str(index),
            'data-ada-alarm-anchor-kind': point.anchor_kind.value,
            'data-ada-alarm-anchor-key': point.anchor_key,
            'data-ada-component-key': point.component_key,
            'data-ada-scope': point.scope.value,
        },
    )
