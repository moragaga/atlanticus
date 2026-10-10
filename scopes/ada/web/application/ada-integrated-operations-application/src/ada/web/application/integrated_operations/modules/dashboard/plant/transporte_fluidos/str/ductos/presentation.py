from __future__ import annotations

from collections.abc import Sequence

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon
from ada.web.ui.equipment_image import (
    EquipmentStateImage,
    LabelPosition,
    build_equipment_state_image,
)

from .definitions import DUCTOS
from .models import StrDuctReading, StrPumpReading


def build_str_ductos(readings: Sequence[StrDuctReading]) -> Component:
    if len(readings) != len(DUCTOS) or not all(
        isinstance(reading, StrDuctReading) for reading in readings
    ):
        raise ValueError('STR requires exactly two ducts')
    return html.Section(
        [
            html.H3('Ductos STR', className='ada-io-str__section-title'),
            html.Div([_duct(item) for item in readings], className='ada-io-str__ducts'),
        ],
        className='ada-io-str__ducts-section',
    )


def _duct(reading: StrDuctReading) -> Component:
    if len(reading.pumps) != len(reading.definition.pumps):
        raise ValueError('STR pump count is inconsistent')
    return html.Div(
        [
            html.Div(
                [
                    html.Span('Ducto'),
                    html.Strong(reading.definition.label),
                    html.Span('"'),
                ],
                className='ada-io-str__duct-header',
            ),
            html.Div(
                build_equipment_state_image(
                    EquipmentStateImage(image='str', state=reading.state)
                ),
                className='ada-io-str__duct-image',
                role='button',
                tabIndex=0,
                title=reading.definition.state_kpi_key,
                **{'data-kpi-inspection-key': reading.definition.state_kpi_key},
            ),
            html.Div(
                [
                    _solids(reading.solids_in, reading.definition.solids_in_kpi_key),
                    html.Span('→'),
                    html.Span('Sólido'),
                    html.Span('→'),
                    _solids(reading.solids_out, reading.definition.solids_out_kpi_key),
                ],
                className='ada-io-str__duct-solids',
            ),
            html.Div([_pump(item) for item in reading.pumps], className='ada-io-str__pumps'),
        ],
        className='ada-io-str__duct',
    )


def _solids(value: DisplayValue, key: str) -> Component:
    return html.Span(
        [html.Strong(_display(value)), html.Span('%')],
        className='ada-io-str__solid-reading',
        role='button',
        tabIndex=0,
        title=key,
        **{'data-kpi-inspection-key': key},
    )


def _pump(reading: StrPumpReading) -> Component:
    return html.Div(
        build_equipment_state_image(
            EquipmentStateImage(
                image='bomba',
                state=reading.state,
                label=reading.definition.label,
                label_position=LabelPosition.BOTTOM,
            )
        ),
        className='ada-io-str__pump',
        role='button',
        tabIndex=0,
        title=reading.definition.state_kpi_key,
        **{'data-kpi-inspection-key': reading.definition.state_kpi_key},
    )


def _display(value: DisplayValue) -> str | Component:
    if value.status is DisplayStatus.OK:
        return str(value.value)
    icon = build_display_status_icon(value.status, class_name='ada-io-str__status-icon')
    if icon is None:
        raise ValueError('STR status icon cannot be resolved')
    return icon
