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

from .definitions import ESPESADORES
from .models import EspesadorMetricReading, EspesadorReading


def build_espesadores(readings: Sequence[EspesadorReading]) -> Component:
    if len(readings) != len(ESPESADORES) or not all(
        isinstance(reading, EspesadorReading) for reading in readings
    ):
        raise ValueError('Selectiva requires exactly five espesadores')
    return html.Section(
        [
            html.H3('Espesadores', className='ada-io-selectiva__section-title'),
            html.Div(
                [_espesador(reading) for reading in readings],
                className='ada-io-selectiva__tanks',
            ),
        ],
        className='ada-io-selectiva__espesadores',
    )


def _espesador(reading: EspesadorReading) -> Component:
    if len(reading.metrics) != len(reading.definition.metrics):
        raise ValueError('Espesador requires four metrics')
    return html.Div(
        [
            html.Div(
                [
                    _feed(reading),
                    html.Div(
                        build_equipment_state_image(
                            EquipmentStateImage(
                                image='espesador',
                                state=reading.state,
                                label=reading.definition.label,
                                label_position=LabelPosition.BOTTOM,
                            )
                        ),
                        className='ada-io-selectiva__machine',
                        role='button',
                        tabIndex=0,
                        title=reading.definition.state_kpi_key,
                        **{'data-kpi-inspection-key': reading.definition.state_kpi_key},
                    ),
                ],
                className='ada-io-selectiva__tank-left',
            ),
            html.Div(
                [_metric(metric) for metric in reading.metrics],
                className='ada-io-selectiva__tank-metrics',
            ),
        ],
        className='ada-io-selectiva__tank',
    )


def _feed(reading: EspesadorReading) -> Component:
    value = reading.feed
    if value.status is DisplayStatus.OK:
        visual = html.Span(
            className=f'ada-io-selectiva__feed-circle ada-io-selectiva__feed-circle--{value.value}',
            role='img',
            **{'aria-label': 'Alimentando' if value.value == 'operando' else 'No alimentando'},
        )
    else:
        visual = _icon(value.status)
    return html.Div(
        visual,
        className='ada-io-selectiva__feed',
        role='button',
        tabIndex=0,
        title=reading.definition.feed_kpi_key,
        **{'data-kpi-inspection-key': reading.definition.feed_kpi_key},
    )


def _metric(reading: EspesadorMetricReading) -> Component:
    definition = reading.definition
    return html.Div(
        [
            html.Span(f'{definition.label} ({definition.unit})'),
            html.Span(_display(reading.value), className='ada-io-selectiva__metric-value'),
        ],
        className='ada-io-selectiva__tank-metric',
        role='button',
        tabIndex=0,
        title=definition.kpi_key,
        **{'data-kpi-inspection-key': definition.kpi_key},
    )


def _display(value: DisplayValue) -> str | Component:
    if value.status is DisplayStatus.OK:
        return str(value.value)
    return _icon(value.status)


def _icon(status: DisplayStatus) -> Component:
    icon = build_display_status_icon(status, class_name='ada-io-selectiva__status-icon')
    if icon is None:
        raise ValueError('Selectiva status icon cannot be resolved')
    return icon
