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

from .definitions import STR_ESPESADORES
from .models import StrEspesadorReading, StrMetricReading


def build_str_espesadores(readings: Sequence[StrEspesadorReading]) -> Component:
    if len(readings) != len(STR_ESPESADORES) or not all(
        isinstance(reading, StrEspesadorReading) for reading in readings
    ):
        raise ValueError('STR requires exactly three espesadores')
    return html.Section(
        [
            html.H3('Espesadores', className='ada-io-str__section-title'),
            html.Div([_espesador(item) for item in readings], className='ada-io-str__tanks'),
        ],
        className='ada-io-str__espesadores',
    )


def _espesador(reading: StrEspesadorReading) -> Component:
    if len(reading.metrics) != 4:
        raise ValueError('STR espesador requires four readings')
    return html.Div(
        [
            html.Div(
                [
                    _feeding(reading),
                    html.Div(
                        build_equipment_state_image(
                            EquipmentStateImage(
                                image='espesador',
                                state=reading.state,
                                label=reading.definition.label,
                                label_position=LabelPosition.BOTTOM,
                            )
                        ),
                        className='ada-io-str__tank-image',
                        role='button',
                        tabIndex=0,
                        title=reading.definition.state_kpi_key,
                        **{'data-kpi-inspection-key': reading.definition.state_kpi_key},
                    ),
                ],
                className='ada-io-str__tank-left',
            ),
            html.Div(
                [_metric(item) for item in reading.metrics],
                className='ada-io-str__tank-metrics',
            ),
        ],
        className='ada-io-str__tank',
    )


def _feeding(reading: StrEspesadorReading) -> Component:
    feed = reading.feed
    if feed.status is DisplayStatus.OK:
        visual = html.Span(
            className=f'ada-io-str__feed-circle ada-io-str__feed-circle--{feed.value}',
            role='img',
            **{'aria-label': 'Alimentando' if feed.value == 'operando' else 'No alimentando'},
        )
    else:
        visual = _icon(feed.status)
    return html.Div(
        visual,
        className='ada-io-str__feed',
        role='button',
        tabIndex=0,
        title=reading.definition.feed_kpi_key,
        **{'data-kpi-inspection-key': reading.definition.feed_kpi_key},
    )


def _metric(reading: StrMetricReading) -> Component:
    definition = reading.definition
    label = (
        definition.label if definition.unit is None else f'{definition.label} ({definition.unit})'
    )
    return html.Div(
        [
            html.Span(label),
            html.Span(_display(reading.value), className='ada-io-str__metric-value'),
        ],
        className='ada-io-str__tank-metric',
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
    icon = build_display_status_icon(status, class_name='ada-io-str__status-icon')
    if icon is None:
        raise ValueError('STR status icon cannot be resolved')
    return icon
