from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)
from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon
from ada.web.ui.inline_row import (
    InlineValueRowDefinition,
    InlineValueRowState,
    InlineValueRowTone,
    build_inline_value_row,
)
from ada.web.ui.time_series import build_time_series_component

from .definitions import MOLIENDA_GENERAL_METRICS, MOLIENDA_TREND
from .models import MoliendaMetricReading, MoliendaOverviewReading


def build_molienda_overview(reading: MoliendaOverviewReading) -> Component:
    if not isinstance(reading, MoliendaOverviewReading):
        raise TypeError('reading must be MoliendaOverviewReading')
    if len(reading.general) != len(MOLIENDA_GENERAL_METRICS):
        raise ValueError('Molienda requires exactly four general metrics')
    return html.Div(
        [
            _trend(reading),
            html.Div(
                [_metric(item) for item in reading.general],
                className='ada-io-molienda__general',
            ),
        ],
        className='ada-io-molienda__overview',
    )


def _trend(state: MoliendaOverviewReading) -> Component:
    return html.Div(
        [
            html.Div(
                [
                    html.Span(MOLIENDA_TREND.label),
                    _inspection(
                        state.trend_current,
                        MOLIENDA_TREND.kpi_key,
                        'ada-io-molienda__trend-value',
                    ),
                ],
                className='ada-io-molienda__trend-header',
            ),
            build_time_series_component(state.trend_history),
        ],
        className='ada-io-molienda__trend',
    )


def _metric(reading: MoliendaMetricReading) -> Component:
    definition = reading.definition
    return html.Div(
        build_inline_value_row(
            InlineValueRowState(
                definition=InlineValueRowDefinition(definition.label, unit=definition.unit),
                value=_display(reading.value),
                tone=_tone(reading.tone),
            )
        ),
        className='ada-io-molienda__metric',
        role='button',
        tabIndex=0,
        title=definition.kpi_key,
        **{'data-kpi-inspection-key': definition.kpi_key},
    )


def _tone(value: DashboardValueStatus) -> InlineValueRowTone:
    label = 'default' if value is DashboardValueStatus.NEUTRAL else value.value
    return InlineValueRowTone(label)


def _inspection(value: DisplayValue, key: str, class_name: str) -> Component:
    return html.Span(
        _display(value),
        className=class_name,
        role='button',
        tabIndex=0,
        title=key,
        **{'data-kpi-inspection-key': key},
    )


def _display(value: DisplayValue) -> str | Component:
    if value.status is DisplayStatus.OK:
        return str(value.value)
    icon = build_display_status_icon(value.status, class_name='ada-io-molienda__status-icon')
    if icon is None:
        raise ValueError('Molienda display status icon cannot be resolved')
    return icon
