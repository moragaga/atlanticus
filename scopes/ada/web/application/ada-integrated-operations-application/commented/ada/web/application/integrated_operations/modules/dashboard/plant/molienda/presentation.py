# Compone la card: tendencia completa, cuatro filas verticales y cuatro líneas SAG.
from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)
from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon
from ada.web.ui.equipment_image import EquipmentStateImage, build_equipment_state_image
from ada.web.ui.inline_row import (
    InlineValueRowDefinition,
    InlineValueRowState,
    InlineValueRowTone,
    build_inline_value_row,
)
from ada.web.ui.time_series import build_time_series_component

from .definitions import MOLIENDA_GENERAL_METRICS, MOLIENDA_LINES, MOLIENDA_TREND
from .models import (
    MoliendaEquipmentReading,
    MoliendaLineReading,
    MoliendaMetricReading,
    MoliendaState,
)


def build_molienda(state: MoliendaState) -> Component:
    if not isinstance(state, MoliendaState):
        raise TypeError('state must be MoliendaState')
    if len(state.general) != len(MOLIENDA_GENERAL_METRICS):
        raise ValueError('Molienda requires exactly four general metrics')
    if len(state.lines) != len(MOLIENDA_LINES):
        raise ValueError('Molienda requires exactly four SAG lines')
    return html.Section(
        [
            _trend(state),
            html.Div(
                [_metric(item) for item in state.general],
                className='ada-io-molienda__general',
            ),
            html.Div([_line(item) for item in state.lines], className='ada-io-molienda__lines'),
        ],
        className='ada-io-molienda',
    )


# Nombre y valor aparecen encima de la tendencia horizontal completa.
def _trend(state: MoliendaState) -> Component:
    return html.Div(
        [
            html.Div(
                [
                    html.Span(MOLIENDA_TREND.label),
                    _inspection(
                        state.trend_current,
                        MOLIENDA_TREND.kpi_key,
                        'ada-io-molienda__trend-value',
                    ),
                ],
                className='ada-io-molienda__trend-header',
            ),
            build_time_series_component(state.trend_history),
        ],
        className='ada-io-molienda__trend',
    )


def _metric(reading: MoliendaMetricReading) -> Component:
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


# SAG centrado; métricas a la izquierda y molinos a la derecha (el cuarto solo MB-010).
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


# Reutiliza las imágenes operacionales y añade manualmente la potencia en kW.
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


def _power_class(tone: DashboardValueStatus) -> str:
    if tone is DashboardValueStatus.NEUTRAL:
        return 'ada-io-molienda__power-value'
    return f'ada-io-molienda__power-value ada-io-molienda__power-value--{tone.value}'


def _tone(value: DashboardValueStatus) -> InlineValueRowTone:
    label = 'default' if value is DashboardValueStatus.NEUTRAL else value.value
    return InlineValueRowTone(label)


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
