from __future__ import annotations

from collections.abc import Sequence

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import (
    DisplayStatus,
    DisplayValue,
    ValueSeverity,
    build_display_status_icon,
)
from ada.web.ui.equipment_image import EquipmentStateImage, build_equipment_state_image
from ada.web.ui.inline_row import (
    InlineValueRowDefinition,
    InlineValueRowState,
    InlineValueRowTone,
    build_inline_value_row,
)

from .definitions import MOLIENDA_LINES
from .models import MoliendaEquipmentReading, MoliendaLineReading, MoliendaSagMetricReading


def build_molienda_sags(readings: Sequence[MoliendaLineReading]) -> Component:
    if len(readings) != len(MOLIENDA_LINES):
        raise ValueError('Molienda requires exactly four SAG lines')
    return html.Div(
        [_line(reading) for reading in readings],
        className='ada-io-molienda__lines',
    )


def _line(reading: MoliendaLineReading) -> Component:
    return html.Section(
        [
            html.H3(f'Línea {reading.definition.number}', className='ada-io-molienda__line-title'),
            html.Div(_equipment(reading.sag), className='ada-io-molienda__sag'),
            html.Div(
                [
                    html.Div(
                        [_metric(item) for item in reading.metrics],
                        className='ada-io-molienda__line-metrics',
                    ),
                    html.Div(
                        [_equipment(mill) for mill in reading.mills],
                        className='ada-io-molienda__mills',
                    ),
                ],
                className='ada-io-molienda__line-details',
            ),
        ],
        className='ada-io-molienda__line',
    )


def _equipment(reading: MoliendaEquipmentReading) -> Component:
    definition = reading.definition
    return html.Div(
        [
            html.Div(
                build_equipment_state_image(
                    EquipmentStateImage(
                        image=definition.image,
                        state=reading.state,
                        label=definition.label,
                    )
                ),
                className='ada-io-molienda__equipment-image',
                role='button',
                tabIndex=0,
                title=definition.state_kpi_key,
                **{'data-kpi-inspection-key': definition.state_kpi_key},
            ),
            html.Div(
                [
                    _inspection(
                        reading.power,
                        definition.power_kpi_key,
                        _power_class(reading.power_tone),
                    ),
                    html.Span('kW', className='ada-io-molienda__power-unit'),
                ],
                className='ada-io-molienda__power',
            ),
        ],
        className='ada-io-molienda__equipment',
    )


def _power_class(tone: ValueSeverity) -> str:
    if tone is ValueSeverity.NEUTRAL:
        return 'ada-io-molienda__power-value'
    return f'ada-io-molienda__power-value ada-io-molienda__power-value--{tone.value}'


def _tone(value: ValueSeverity) -> InlineValueRowTone:
    label = 'default' if value is ValueSeverity.NEUTRAL else value.value
    return InlineValueRowTone(label)


def _metric(reading: MoliendaSagMetricReading) -> Component:
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
