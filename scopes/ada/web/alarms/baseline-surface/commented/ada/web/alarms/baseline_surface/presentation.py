# Espejo comentado de la superficie estática del baseline de alarmas ADA.

from __future__ import annotations

from dash import html

from ada.web.alarms.baseline_projection import AlarmBaselinePoint, AlarmBaselineProjection


# La composición visual toma el lenguaje de Operational Trace: línea, capa de puntos y posiciones
# porcentuales. No incorpora todavía rutas, tarjetas, preview, selección ni estados vivos.
def build_alarm_baseline_surface(projection: AlarmBaselineProjection) -> html.Div:
    if not isinstance(projection, AlarmBaselineProjection):
        raise TypeError('Alarm Baseline Projection is required')

    traces = [
        _build_trace(
            points=projection.main_points,
            region='main',
        )
    ]
    if projection.bottom_point is not None:
        traces.append(
            _build_trace(
                points=(projection.bottom_point,),
                region='bottom',
            )
        )

    # Los atributos conservan identidad operacional para que el motor pueda enlazarla después.
    attributes = {
        'aria-hidden': 'true',
        'data-ada-alarm-baseline': projection.kind.value,
        'data-ada-alarm-baseline-tool-key': projection.tool_key,
        'data-ada-alarm-baseline-main-point-count': str(len(projection.main_points)),
        'data-ada-alarm-baseline-point-count': str(len(projection.points)),
    }
    if projection.bottom_component_key is not None:
        attributes['data-ada-alarm-baseline-bottom-component-key'] = (
            projection.bottom_component_key
        )

    class_name = (
        'ada-alarm-baseline-surface '
        f'ada-alarm-baseline-surface--{projection.kind.value.replace("_", "-")}'
    )
    if projection.bottom_point is not None:
        class_name = f'{class_name} ada-alarm-baseline-surface--has-bottom'

    return html.Div(
        traces,
        className=class_name,
        **attributes,
    )


def _build_trace(
    *,
    points: tuple[AlarmBaselinePoint, ...],
    region: str,
) -> html.Div:
    return html.Div(
        [
            html.Div(className='ada-alarm-baseline-surface__baseline'),
            html.Div(
                [
                    _build_point(
                        point,
                        index=index,
                        point_count=len(points),
                        region=region,
                    )
                    for index, point in enumerate(points)
                ],
                className='ada-alarm-baseline-surface__points',
            ),
        ],
        className=(
            'ada-alarm-baseline-surface__trace '
            f'ada-alarm-baseline-surface__trace--{region}'
        ),
        **{'data-ada-alarm-baseline-region': region},
    )


def _build_point(
    point: AlarmBaselinePoint,
    *,
    index: int,
    point_count: int,
    region: str,
) -> html.Div:
    # Igual que en Operational Trace, cada punto ocupa el centro de su slot relativo.
    position_percent = ((index + 0.5) / point_count) * 100
    return html.Div(
        html.Span(className='ada-alarm-baseline-surface__point-core'),
        className='ada-alarm-baseline-surface__point',
        style={
            '--ada-alarm-baseline-point-x': f'{position_percent:.6f}%',
        },
        **{
            'data-ada-alarm-baseline-index': str(index),
            'data-ada-alarm-baseline-region': region,
            'data-ada-alarm-anchor-kind': point.anchor_kind.value,
            'data-ada-alarm-anchor-key': point.anchor_key,
            'data-ada-component-key': point.component_key,
            'data-ada-scope': point.scope.value,
        },
    )
