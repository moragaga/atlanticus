# Cada Feeder usa su propia figura Plotly de altura compacta y mantiene el porcentaje real.
# Los estados degradados conservan el icono e inspección individual.
# El color inválido no impide dibujar la barra: se utiliza el gris neutro.
from __future__ import annotations

import plotly.graph_objects as go
from dash import dcc, html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, build_display_status_icon

from .models import FeederColor, FeederValues

_COLORS = {
    FeederColor.NEUTRAL: '#939393',
    FeederColor.DANGER: '#c62828',
    FeederColor.WARNING: '#d3a000',
}


def build_feeder_component(
    label: str,
    values: FeederValues,
    *,
    inspection_key: str,
) -> Component:
    if not isinstance(label, str) or not label.strip():
        raise ValueError('Feeder label must be a non-empty string')
    if not isinstance(inspection_key, str) or not inspection_key.strip():
        raise ValueError('Feeder inspection_key must be a non-empty string')
    if not isinstance(values, FeederValues):
        raise TypeError('Feeder values must be FeederValues')

    if values.percent.status is DisplayStatus.OK:
        percent = values.percent.value
        graphic = dcc.Graph(
            figure=_figure(percent, _color(values)),
            config={'displayModeBar': False, 'staticPlot': True, 'responsive': True},
            responsive=True,
            className='ada-feeder__graph',
        )
        reading = html.Span(f'{percent}%', className='ada-feeder__value')
    else:
        graphic = build_display_status_icon(
            values.percent.status, class_name='ada-feeder__status-icon'
        )
        reading = None
    return html.Div(
        [
            html.Div(graphic, className='ada-feeder__graphic'),
            *([] if reading is None else [reading]),
            html.Span(label, className='ada-feeder__label'),
        ],
        className='ada-feeder',
        role='button',
        tabIndex=0,
        title=inspection_key,
        **{'data-kpi-inspection-key': inspection_key},
    )


def _color(values: FeederValues) -> str:
    color = values.color
    if color is None or color.status is not DisplayStatus.OK:
        return _COLORS[FeederColor.NEUTRAL]
    return _COLORS[color.value]


def _figure(percent: int, color: str) -> go.Figure:
    figure = go.Figure(
        go.Bar(
            x=['feeder'],
            y=[min(percent, 100)],
            marker_color=color,
            width=[0.7],
            hoverinfo='skip',
            showlegend=False,
        )
    )
    figure.update_layout(
        showlegend=False,
        height=52,
        margin={'l': 0, 'r': 0, 't': 0, 'b': 0},
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis={'visible': False, 'fixedrange': True},
        yaxis={'visible': False, 'fixedrange': True, 'range': [0, 100]},
        bargap=0,
    )
    return figure
