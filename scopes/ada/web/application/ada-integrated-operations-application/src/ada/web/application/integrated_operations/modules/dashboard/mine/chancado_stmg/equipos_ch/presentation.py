from __future__ import annotations

from collections.abc import Sequence

from dash import html
from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)
from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon
from ada.web.ui.equipment_image import EquipmentStateImage, build_equipment_state_image
from ada.web.ui.feeder import FeederValues, build_feeder_component

from .models import EquiposChReading, FeederKpiDefinition


def build_equipos_ch(readings: Sequence[EquiposChReading]) -> Component:
    if not isinstance(readings, Sequence) or not all(
        isinstance(reading, EquiposChReading) for reading in readings
    ):
        raise TypeError('readings must be a sequence of EquiposChReading')
    if len(readings) != 2:
        raise ValueError('Equipos CH requires exactly two readings')
    left, right = readings
    return html.Section(
        [
            html.H3('EQUIPOS CH', className='ada-io-equipos-ch__title'),
            html.Div(
                [
                    _image(left),
                    _details(left),
                    _details(right),
                    _image(right),
                ],
                className='ada-io-equipos-ch__body',
            ),
            _metrics_table(readings),
        ],
        className='ada-io-equipos-ch',
    )



def _metrics_table(readings: Sequence[EquiposChReading]) -> Component:
    return html.Table(
        [
            html.Thead(
                html.Tr([
                    html.Th('EQUIPO', scope='col'),
                    html.Th('RENDIMIENTO', scope='col'),
                    html.Th('MIN. ATOLLO', scope='col'),
                    html.Th('MIN. POSTE', scope='col'),
                ])
            ),
            html.Tbody([_metrics_row(reading) for reading in readings]),
        ],
        className='ada-io-equipos-ch__table',
    )


def _metrics_row(reading: EquiposChReading) -> Component:
    definition = reading.definition
    return html.Tr([
        html.Th(definition.label, scope='row'),
        html.Td(_table_metric(
            reading.rendimiento, definition.rendimiento_kpi_key,
            reading.rendimiento_color, definition.rendimiento_color_kpi_key,
        )),
        html.Td(_table_metric(
            reading.min_atollo, definition.min_atollo_kpi_key,
            reading.min_atollo_color, definition.min_atollo_color_kpi_key,
        )),
        html.Td(_table_metric(
            reading.min_poste, definition.min_poste_kpi_key,
            reading.min_poste_color, definition.min_poste_color_kpi_key,
        )),
    ])


def _image(reading: EquiposChReading) -> Component:
    return html.Div(
        build_equipment_state_image(EquipmentStateImage(image='chancador', state=reading.state)),
        className='ada-io-equipos-ch__image-target',
        role='button',
        tabIndex=0,
        title=reading.definition.state_kpi_key,
        **{'data-kpi-inspection-key': reading.definition.state_kpi_key},
    )


def _details(reading: EquiposChReading) -> Component:
    definition = reading.definition
    atollo = _atollo(reading.atollo, definition.atollo_kpi_key)
    return html.Div(
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
    )


def _table_metric(
    value: DisplayValue,
    value_key: str,
    color: DisplayValue | None,
    color_key: str | None,
) -> Component:
    if color_key is None:
        return _metric(value, value_key)
    if color is None:
        raise ValueError('Configured Equipos CH color requires a reading')
    return html.Span(
        [
            _metric(value, value_key, color=color),
            _color_indicator(color, color_key),
        ],
        className='ada-io-equipos-ch__table-metric',
    )


def _color_indicator(color: DisplayValue, key: str) -> Component:
    class_name = 'ada-io-equipos-ch__color-indicator'
    if color.status is DisplayStatus.OK:
        state = color.value
        if not isinstance(state, DashboardValueStatus):
            raise ValueError('Equipos CH color state must be DashboardValueStatus')
        class_name += f' ada-io-equipos-ch__color-indicator--{state.value}'
        child = html.Span(className='ada-io-equipos-ch__color-dot', **{'aria-hidden': 'true'})
    else:
        child = _display(color)
    return html.Span(
        child,
        className=class_name,
        role='button',
        tabIndex=0,
        title=key,
        **{'data-kpi-inspection-key': key},
    )


def _metric(
    value: DisplayValue,
    key: str,
    *,
    color: DisplayValue | None = None,
) -> Component:
    class_name = 'ada-io-equipos-ch__value'
    if value.status is DisplayStatus.OK and color is not None and color.status is DisplayStatus.OK:
        state = color.value
        if not isinstance(state, DashboardValueStatus):
            raise ValueError('Equipos CH color state must be DashboardValueStatus')
        class_name += f' ada-io-equipos-ch__value--{state.value}'
    return html.Span(
        _display(value),
        className=class_name,
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
    icon = build_display_status_icon(
        value.status,
        class_name='ada-io-equipos-ch__status-icon',
    )
    if icon is None:
        raise ValueError('Equipos CH status icon cannot be resolved')
    return icon


def build_chancado_feeders(
    definitions: Sequence[FeederKpiDefinition],
    values: Sequence[FeederValues],
) -> Component:
    if len(definitions) != 4 or len(values) != len(definitions):
        raise ValueError('Chancado requires exactly four feeders')
    return html.Section(
        [
            html.Div(
                [
                    build_feeder_component(
                        definition.label,
                        reading,
                        inspection_key=definition.percent_kpi_key,
                        graphic_height_px=32,
                    )
                    for definition, reading in zip(definitions, values, strict=True)
                ],
                className='ada-io-feeders__items',
            ),
            html.H3('FEEDERS', className='ada-io-feeders__title'),
        ],
        className='ada-io-feeders',
    )
