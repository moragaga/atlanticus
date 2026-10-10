from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon
from ada.web.ui.time_series import build_time_series_component

from .definitions import STR_TREND
from .models import StrOverviewReading


def build_str_overview(reading: StrOverviewReading) -> Component:
    if not isinstance(reading, StrOverviewReading):
        raise TypeError('reading must be StrOverviewReading')
    return html.Section(
        [
            html.Div(
                [
                    html.Span(STR_TREND.label),
                    html.Div(
                        [
                            html.Span(
                                _display(reading.current),
                                role='button',
                                tabIndex=0,
                                title=STR_TREND.kpi_key,
                                **{'data-kpi-inspection-key': STR_TREND.kpi_key},
                            ),
                            html.Span(STR_TREND.unit),
                        ],
                        className='ada-io-str__trend-reading',
                    ),
                ],
                className='ada-io-str__trend-header',
            ),
            build_time_series_component(reading.history),
        ],
        className='ada-io-str__trend',
    )


def _display(value: DisplayValue) -> str | Component:
    if value.status is DisplayStatus.OK:
        return str(value.value)
    icon = build_display_status_icon(value.status, class_name='ada-io-str__status-icon')
    if icon is None:
        raise ValueError('STR status icon cannot be resolved')
    return icon
