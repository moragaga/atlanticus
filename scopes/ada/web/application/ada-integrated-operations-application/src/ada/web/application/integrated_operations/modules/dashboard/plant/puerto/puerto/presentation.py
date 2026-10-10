from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon
from ada.web.ui.equipment_image import EquipmentStateImage, build_equipment_state_image
from ada.web.ui.inline_row import (
    InlineValueRowDefinition,
    InlineValueRowState,
    build_inline_value_row,
)
from ada.web.ui.level_gauge import build_level_gauge
from ada.web.ui.time_series import build_time_series_component

from .definitions import (
    FILTERS,
    FILTRADO_ACCUMULATED,
    FILTRADO_TREND,
    SHIPMENT,
    TANKS,
    MetricDefinition,
)
from .models import FilterReading, PuertoReading


def build_puerto(reading: PuertoReading) -> Component:
    if not isinstance(reading, PuertoReading):
        raise TypeError('reading must be PuertoReading')
    if len(reading.tanks) != len(TANKS) or len(reading.filters) != len(FILTERS):
        raise ValueError('Puerto equipment counts are inconsistent')
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(FILTRADO_TREND.label),
                            _inspect(reading.trend_current, FILTRADO_TREND.kpi_key),
                        ],
                        className='ada-io-puerto__trend-header',
                    ),
                    build_time_series_component(reading.trend_history),
                ],
                className='ada-io-puerto__trend',
            ),
            _row(FILTRADO_ACCUMULATED, reading.accumulated),
            html.Div(
                [
                    _inspect_wrap(build_level_gauge(view), definition.level_key)
                    for definition, view in zip(TANKS, reading.tanks, strict=True)
                ],
                className='ada-io-puerto__tanks',
            ),
            html.Section(
                [
                    html.H3('Filtros', className='ada-io-puerto__section-title'),
                    html.Div([_filter(item) for item in reading.filters], className='ada-io-puerto__filters'),
                ],
                className='ada-io-puerto__section',
            ),
            html.Section(
                [
                    html.H3('Embarque', className='ada-io-puerto__section-title'),
                    html.Div(
                        [
                            html.Div(
                                [
                                    _row(SHIPMENT.tonnage, reading.tonnage),
                                    _row(
                                        MetricDefinition('Tiempo', SHIPMENT.duration_key, reading.duration_unit or None),
                                        reading.duration,
                                    ),
                                ],
                                className='ada-io-puerto__shipment-rows',
                            ),
                            _inspect_wrap(_image('barco', reading.ship_state), SHIPMENT.state_key),
                        ],
                        className='ada-io-puerto__shipment',
                    ),
                ],
                className='ada-io-puerto__section',
            ),
        ],
        className='ada-io-puerto',
    )


def _filter(reading: FilterReading) -> Component:
    return _inspect_wrap(
        html.Div(
            [
                html.Span(reading.definition.label, className='ada-io-puerto__filter-label'),
                _image('filtro', reading.state),
            ],
            className='ada-io-puerto__filter',
        ),
        reading.definition.state_key,
    )


def _image(kind: str, value: DisplayValue) -> Component:
    return build_equipment_state_image(
        EquipmentStateImage(
            image=kind,
            state=value,
            image_class_name=f'ada-io-puerto__image ada-io-puerto__image--{kind}',
        )
    )


def _row(definition, value: DisplayValue) -> Component:
    return _inspect_wrap(
        build_inline_value_row(
            InlineValueRowState(
                InlineValueRowDefinition(definition.label, unit=definition.unit),
                _display(value),
            )
        ),
        definition.kpi_key,
    )


def _inspect(value: DisplayValue, key: str) -> Component:
    return html.Span(
        _display(value),
        role='button',
        tabIndex=0,
        title=key,
        **{'data-kpi-inspection-key': key},
    )


def _inspect_wrap(component: Component, key: str) -> Component:
    return html.Div(
        component,
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
        raise ValueError('Puerto status icon cannot be resolved')
    return icon
