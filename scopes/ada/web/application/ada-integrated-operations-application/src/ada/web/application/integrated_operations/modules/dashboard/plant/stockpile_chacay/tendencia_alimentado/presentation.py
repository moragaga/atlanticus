from __future__ import annotations

from collections.abc import Sequence

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, build_display_status_icon
from ada.web.ui.time_series import build_time_series_component

from .definitions import ALIMENTADO_TRENDS
from .models import AlimentadoTrendReading


def build_tendencia_alimentado(readings: Sequence[AlimentadoTrendReading]) -> Component:
    if len(readings) != len(ALIMENTADO_TRENDS):
        raise ValueError('Tendencia Alimentado requires exactly three series')
    return html.Section(
        [_trend(reading) for reading in readings],
        className='ada-io-alimentado',
    )


def _trend(reading: AlimentadoTrendReading) -> Component:
    current = reading.current
    if current.status is DisplayStatus.OK:
        indicator = html.Span(str(current.value), className='ada-io-alimentado__value')
    else:
        indicator = build_display_status_icon(
            current.status, class_name='ada-io-alimentado__status-icon'
        )
    return html.Div(
        [
            html.Div(
                [
                    html.Span(reading.definition.label, className='ada-io-alimentado__label'),
                    indicator,
                ],
                className='ada-io-alimentado__heading',
            ),
            build_time_series_component(reading.history),
        ],
        className='ada-io-alimentado__trend',
        role='button',
        tabIndex=0,
        title=reading.definition.kpi_key,
        **{'data-kpi-inspection-key': reading.definition.kpi_key},
    )
