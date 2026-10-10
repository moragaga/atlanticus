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

from .definitions import FLUJO_TREND, VOLUMEN
from .models import DesaladoraReading


# Coordina las dos presentaciones sin mezclar su lógica específica.
def build_desaladora(reading: DesaladoraReading) -> Component:
    if not isinstance(reading, DesaladoraReading):
        raise TypeError('reading must be DesaladoraReading')
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(FLUJO_TREND.label),
                            html.Span(
                                _display(reading.trend_current),
                                role='button',
                                tabIndex=0,
                                title=FLUJO_TREND.kpi_key,
                                **{'data-kpi-inspection-key': FLUJO_TREND.kpi_key},
                            ),
                        ],
                        className='ada-io-desaladora__trend-header',
                    ),
                    build_time_series_component(reading.trend_history),
                ],
                className='ada-io-desaladora__trend',
            ),
            html.Div(
                build_inline_value_row(
                    InlineValueRowState(
                        InlineValueRowDefinition(VOLUMEN.label, unit=VOLUMEN.unit),
                        _display(reading.volume),
                    )
                ),
                role='button',
                tabIndex=0,
                title=VOLUMEN.kpi_key,
                **{'data-kpi-inspection-key': VOLUMEN.kpi_key},
            ),
        ],
        className='ada-io-desaladora',
    )


def _display(value: DisplayValue) -> str | Component:
    if value.status is DisplayStatus.OK:
        return str(value.value)
    icon = build_display_status_icon(value.status)
    if icon is None:
        raise ValueError('Desaladora status icon cannot be resolved')
    return icon
