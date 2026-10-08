from __future__ import annotations

from collections.abc import Sequence

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon
from ada.web.ui.equipment_image import EquipmentStateImage, build_equipment_state_image

from .models import EquiposChReading


def build_equipos_ch(readings: Sequence[EquiposChReading]) -> Component:
    if not isinstance(readings, Sequence) or not all(
        isinstance(reading, EquiposChReading) for reading in readings
    ):
        raise TypeError('readings must be a sequence of EquiposChReading')
    return html.Section(
        [
            html.H3('EQUIPOS CH', className='ada-io-equipos-ch__title'),
            html.Div([_equipment(reading) for reading in readings], className='ada-io-equipos-ch__rows'),
        ],
        className='ada-io-equipos-ch',
    )


def _equipment(reading: EquiposChReading) -> Component:
    definition = reading.definition
    atollo = _atollo(reading.atollo, definition.atollo_kpi_key)
    children = [
        html.Div(
            build_equipment_state_image(EquipmentStateImage(image='chancador', state=reading.state)),
            className='ada-io-equipos-ch__image-target',
            role='button',
            tabIndex=0,
            title=definition.state_kpi_key,
            **{'data-kpi-inspection-key': definition.state_kpi_key},
        ),
        html.Div(
            [
                html.Span(definition.label, className='ada-io-equipos-ch__label'),
                html.Div(
                    [
                        _metric(reading.throughput, definition.throughput_kpi_key),
                        html.Span('t/h', className='ada-io-equipos-ch__unit'),
                    ],
                    className='ada-io-equipos-ch__throughput',
                ),
                *([] if atollo is None else [atollo]),
            ],
            className='ada-io-equipos-ch__details',
        ),
    ]
    return html.Div(children, className='ada-io-equipos-ch__equipment')


def _metric(value: DisplayValue, key: str) -> Component:
    return html.Span(
        _display(value),
        className='ada-io-equipos-ch__value',
        role='button',
        tabIndex=0,
        title=key,
        **{'data-kpi-inspection-key': key},
    )


def _atollo(value: DisplayValue, key: str) -> Component | None:
    if value.status is DisplayStatus.OK:
        if value.value is False:
            return None
        if value.value is not True:
            raise ValueError('Equipos CH atollo must be boolean')
        children = [
            html.Span(className='ada-io-equipos-ch__atollo-dot', **{'aria-hidden': 'true'}),
            html.Span('ATOLLO'),
        ]
        class_name = 'ada-io-equipos-ch__atollo ada-io-equipos-ch__atollo--active'
    else:
        children = [_display(value)]
        class_name = 'ada-io-equipos-ch__atollo'
    return html.Div(
        children,
        className=class_name,
        role='button',
        tabIndex=0,
        title=key,
        **{'data-kpi-inspection-key': key},
    )


def _display(value: DisplayValue) -> str | Component:
    if value.status is DisplayStatus.OK:
        return str(value.value)
    icon = build_display_status_icon(value.status)
    if icon is None:
        raise ValueError('Equipos CH status icon cannot be resolved')
    return icon
