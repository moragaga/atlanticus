from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon
from ada.web.ui.equipment_image import (
    EquipmentStateImage,
    LabelPosition,
    build_equipment_state_image,
)
from ada.web.ui.level_gauge import build_level_gauge

from ..indicators import build_metric_rows, display_value_component
from .definitions import STC_ESPESADOR, STC_LEVELS
from .models import StcReading


# La presentación visual se mantiene; solo cambia el punto de importación de indicadores.
def build_stc(reading: StcReading) -> Component:
    if not isinstance(reading, StcReading):
        raise TypeError('reading must be StcReading')
    if len(reading.levels) != len(STC_LEVELS):
        raise ValueError('STC requires two level indicators')
    return html.Section(
        [
            build_metric_rows(reading.indicators, class_name='ada-io-stc__indicators'),
            html.Section(
                [
                    html.H3('Espesadores', className='ada-io-stc__title'),
                    _espesador(reading.espesador),
                ],
                className='ada-io-stc__section',
            ),
            html.Section(
                [
                    html.H3('Niveles', className='ada-io-stc__title'),
                    html.Div(
                        [
                            html.Div(
                                build_level_gauge(view),
                                className='ada-io-stc__level',
                                role='button',
                                tabIndex=0,
                                title=definition.level_key,
                                **{'data-kpi-inspection-key': definition.level_key},
                            )
                            for definition, view in zip(STC_LEVELS, reading.levels, strict=True)
                        ],
                        className='ada-io-stc__levels',
                    ),
                ],
                className='ada-io-stc__section',
            ),
        ],
        className='ada-io-stc',
    )


def _espesador(reading) -> Component:
    d = reading.definition
    if len(reading.metrics) != len(STC_ESPESADOR.metrics):
        raise ValueError('STC espesador requires four metrics')
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        _feed(reading.feed),
                        className='ada-io-stc__feed',
                        role='button',
                        tabIndex=0,
                        title=d.feed_key,
                        **{'data-kpi-inspection-key': d.feed_key},
                    ),
                    html.Div(
                        build_equipment_state_image(
                            EquipmentStateImage(
                                image='espesador',
                                state=reading.state,
                                label=d.label,
                                label_position=LabelPosition.BOTTOM,
                            )
                        ),
                        className='ada-io-stc__machine',
                        role='button',
                        tabIndex=0,
                        title=d.state_key,
                        **{'data-kpi-inspection-key': d.state_key},
                    ),
                ],
                className='ada-io-stc__tank-left',
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(f'{metric.definition.label} ({metric.definition.unit})'),
                            html.Span(display_value_component(metric.value)),
                        ],
                        className='ada-io-stc__metric',
                        role='button',
                        tabIndex=0,
                        title=metric.definition.kpi_key,
                        **{'data-kpi-inspection-key': metric.definition.kpi_key},
                    )
                    for metric in reading.metrics
                ],
                className='ada-io-stc__metrics',
            ),
        ],
        className='ada-io-stc__tank',
    )


def _feed(value: DisplayValue) -> Component:
    if value.status is DisplayStatus.OK:
        return html.Span(
            className=f'ada-io-stc__feed-circle ada-io-stc__feed-circle--{value.value}',
            role='img',
            **{'aria-label': 'Alimentando' if value.value == 'operando' else 'No alimentando'},
        )
    icon = build_display_status_icon(value.status)
    if icon is None:
        raise ValueError('STC feed icon cannot be resolved')
    return icon
