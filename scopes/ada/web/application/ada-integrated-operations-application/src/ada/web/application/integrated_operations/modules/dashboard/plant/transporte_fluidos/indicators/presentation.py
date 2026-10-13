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

from .models import FluidMetricReading


def build_metric_rows(readings: Sequence[FluidMetricReading], *, class_name: str) -> Component:
    return html.Div(
        [
            html.Div(
                build_inline_value_row(
                    InlineValueRowState(
                        InlineValueRowDefinition(item.definition.label, unit=item.definition.unit),
                        display_value_component(item.value, class_name=f'{class_name}__status-icon'),
                    )
                ),
                role='button',
                tabIndex=0,
                title=item.definition.kpi_key,
                **{'data-kpi-inspection-key': item.definition.kpi_key},
            )
            for item in readings
        ],
        className=f'{class_name}__indicators',
    )


def display_value_component(value: DisplayValue, class_name: str) -> str | Component:
    if value.status is DisplayStatus.OK:
        return str(value.value)
    icon = build_display_status_icon(value.status, class_name=class_name)
    if icon is None:
        raise ValueError('Fluid metric icon cannot be resolved')
    return icon
