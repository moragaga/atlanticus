from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
from dash import dcc, html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, build_display_status_icon

from .models import TimeSeriesValues

_SANTIAGO = ZoneInfo('America/Santiago')


def build_time_series_component(
    series: TimeSeriesValues,
    *,
    height_px: int = 116,
) -> Component:
    if not isinstance(series, TimeSeriesValues):
        raise TypeError('series must be TimeSeriesValues')
    if type(height_px) is not int or height_px <= 0:
        raise ValueError('height_px must be a positive integer')
    if series.status in (DisplayStatus.INVALID, DisplayStatus.ERROR):
        icon = build_display_status_icon(series.status, class_name='ada-time-series__status-icon')
        if icon is None:
            raise ValueError('Time series status icon cannot be resolved')
        return html.Div(icon, className='ada-time-series__unavailable')
    return dcc.Graph(
        figure=_figure(series, height_px),
        config={
            'displayModeBar': False,
            'staticPlot': True,
            'responsive': True,
        },
        responsive=True,
        style={'width': '100%', 'height': f'{height_px}px'},
        className='ada-time-series__graph',
    )


def _figure(series: TimeSeriesValues, height_px: int) -> go.Figure:
    moments = [point.timestamp_utc for point in series.points]
    values = [point.value for point in series.points]
    ticks = _tick_indices(len(moments), 3 if _offset_changes(moments) else 5)
    labels = _santiago_labels([moments[index] for index in ticks], moments)
    xaxis = {
        'type': 'date',
        'tickmode': 'array',
        'tickvals': [moments[index].isoformat() for index in ticks],
        'ticktext': labels,
        'showgrid': False,
        'zeroline': False,
        'showline': True,
        'linecolor': '#757575',
        'linewidth': 1,
        'fixedrange': True,
        'tickfont': {'size': 9},
        'automargin': False,
    }
    if moments:
        start = moments[0] if len(moments) > 1 else moments[0] - timedelta(minutes=1)
        end = moments[-1] if len(moments) > 1 else moments[-1] + timedelta(minutes=1)
        xaxis['range'] = [start.isoformat(), end.isoformat()]
    figure = go.Figure(
        go.Scatter(
            x=[stamp.isoformat() for stamp in moments],
            y=values,
            mode='markers' if sum(value is not None for value in values) == 1 else 'lines',
            connectgaps=False,
            hoverinfo='skip',
            showlegend=False,
            line={'width': 1.4, 'color': '#757575'},
            marker={'size': 4, 'color': '#757575'},
        )
    )
    figure.update_layout(
        autosize=True,
        height=height_px,
        margin={'l': 8, 'r': 8, 't': 5, 'b': 26},
        showlegend=False,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        dragmode=False,
        xaxis=xaxis,
        yaxis={
            'showgrid': False,
            'zeroline': False,
            'showline': True,
            'linecolor': '#757575',
            'linewidth': 1,
            'fixedrange': True,
            'showticklabels': False,
        },
    )
    return figure


def _tick_indices(length: int, count: int) -> list[int]:
    if length <= count:
        return list(range(length))
    return sorted({round(i * (length - 1) / (count - 1)) for i in range(count)})


def _offset_changes(moments: list[datetime]) -> bool:
    return len({stamp.astimezone(_SANTIAGO).utcoffset() for stamp in moments}) > 1


def _santiago_labels(ticks: list[datetime], all_moments: list[datetime]) -> list[str]:
    show_offset = _offset_changes(all_moments)
    labels = []
    for stamp in ticks:
        local = stamp.astimezone(_SANTIAGO)
        label = local.strftime('%H:%M')
        if show_offset:
            offset = local.strftime('%z')
            label += f' UTC{offset[:3]}:{offset[3:]}'
        labels.append(label)
    return labels
