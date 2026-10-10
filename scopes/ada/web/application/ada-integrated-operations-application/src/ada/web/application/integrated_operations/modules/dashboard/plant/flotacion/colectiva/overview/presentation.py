from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon
from ada.web.ui.inline_row import (
    InlineValueRowDefinition,
    InlineValueRowState,
    build_inline_value_row,
)
from ada.web.ui.time_series import build_time_series_component

from .definitions import COLECTIVA_INDICATORS, COLECTIVA_TREND
from .models import ColectivaIndicatorReading, ColectivaOverviewReading


def build_colectiva_overview(reading: ColectivaOverviewReading) -> Component:
    if not isinstance(reading, ColectivaOverviewReading):
        raise TypeError('reading must be ColectivaOverviewReading')
    if len(reading.indicators) != len(COLECTIVA_INDICATORS):
        raise ValueError('Colectiva requires exactly five indicators')
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(COLECTIVA_TREND.label),
                            _inspect(reading.trend_current, COLECTIVA_TREND.kpi_key),
                        ],
                        className='ada-io-colectiva__trend-header',
                    ),
                    build_time_series_component(reading.trend_history),
                ],
                className='ada-io-colectiva__trend',
            ),
            html.Div(
                [_indicator(item) for item in reading.indicators],
                className='ada-io-colectiva__indicators',
            ),
        ],
        className='ada-io-colectiva__overview',
    )


def _indicator(reading: ColectivaIndicatorReading) -> Component:
    definition = reading.definition
    return html.Div(
        build_inline_value_row(
            InlineValueRowState(
                definition=InlineValueRowDefinition(definition.label, unit=definition.unit),
                value=_display(reading.value),
            )
        ),
        className='ada-io-colectiva__indicator',
        role='button',
        tabIndex=0,
        title=definition.kpi_key,
        **{'data-kpi-inspection-key': definition.kpi_key},
    )


def _inspect(value: DisplayValue, key: str) -> Component:
    return html.Span(
        _display(value),
        className='ada-io-colectiva__trend-value',
        role='button',
        tabIndex=0,
        title=key,
        **{'data-kpi-inspection-key': key},
    )


def _display(value: DisplayValue) -> str | Component:
    if value.status is DisplayStatus.OK:
        return str(value.value)
    icon = build_display_status_icon(value.status, class_name='ada-io-colectiva__status-icon')
    if icon is None:
        raise ValueError('Colectiva display status icon cannot be resolved')
    return icon
