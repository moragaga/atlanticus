from __future__ import annotations

from collections.abc import Sequence

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon
from ada.web.ui.inline_row import (
    InlineValueRowDefinition,
    InlineValueRowState,
    build_inline_value_row,
)

from .definitions import SELECTIVA_INDICATORS
from .models import SelectivaIndicatorReading


def build_selectiva_indicators(readings: Sequence[SelectivaIndicatorReading]) -> Component:
    if len(readings) != len(SELECTIVA_INDICATORS) or not all(
        isinstance(reading, SelectivaIndicatorReading) for reading in readings
    ):
        raise ValueError('Selectiva requires exactly six indicators')
    return html.Div(
        [_indicator(reading) for reading in readings],
        className='ada-io-selectiva__indicators',
    )


def _indicator(reading: SelectivaIndicatorReading) -> Component:
    definition = reading.definition
    return html.Div(
        build_inline_value_row(
            InlineValueRowState(
                definition=InlineValueRowDefinition(definition.label, unit=definition.unit),
                value=_display(reading.value),
            )
        ),
        className='ada-io-selectiva__indicator',
        role='button',
        tabIndex=0,
        title=definition.kpi_key,
        **{'data-kpi-inspection-key': definition.kpi_key},
    )


def _display(value: DisplayValue) -> str | Component:
    if value.status is DisplayStatus.OK:
        return str(value.value)
    icon = build_display_status_icon(
        value.status, class_name='ada-io-selectiva__status-icon'
    )
    if icon is None:
        raise ValueError('Selectiva status icon cannot be resolved')
    return icon
