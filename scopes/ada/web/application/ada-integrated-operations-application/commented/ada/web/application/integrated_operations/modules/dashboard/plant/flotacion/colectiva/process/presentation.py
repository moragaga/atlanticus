# Construye componentes Dash usando contratos UI compartidos.
from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon
from ada.web.ui.equipment_image import EquipmentStateImage, build_equipment_state_image
from ada.web.ui.inline_row import (
    InlineComparisonRowDefinition,
    InlineComparisonRowState,
    build_inline_comparison_row,
)

from .definitions import (
    BOMBAS,
    COLUMNS_OPERATING_KEY,
    COLUMNS_TOTAL_KEY,
    ROUGHERS,
    SCAVENGERS,
    VERTIMILLS,
)
from .models import ColectivaEquipmentReading, ColectivaProcessReading, ColectivaStateReading


# El orden sigue Rougher, máquinas, columnas y Scavenger.
def build_colectiva_process(reading: ColectivaProcessReading) -> Component:
    if not isinstance(reading, ColectivaProcessReading):
        raise TypeError('reading must be ColectivaProcessReading')
    if (
        len(reading.roughers) != len(ROUGHERS)
        or len(reading.scavengers) != len(SCAVENGERS)
        or len(reading.vertimills) != len(VERTIMILLS)
        or tuple(map(len, reading.bombas)) != tuple(map(len, BOMBAS))
    ):
        raise ValueError('Colectiva process has an inconsistent equipment count')
    return html.Div(
        [
            _state_group('Rougher (R1–R9)', reading.roughers, 'roughers'),
            html.Section(
                [
                    html.H3('Molinos Verticales', className='ada-io-colectiva__section-title'),
                    html.Div(
                        [
                            html.Div([_equipment(item) for item in reading.vertimills],
                                     className='ada-io-colectiva__vertimills'),
                            html.Div(
                                [
                                    html.Div([_equipment(item) for item in pair],
                                             className='ada-io-colectiva__pump-pair')
                                    for pair in reading.bombas
                                ],
                                className='ada-io-colectiva__bombas',
                            ),
                        ],
                        className='ada-io-colectiva__machines',
                    ),
                    html.Div(
                        build_inline_comparison_row(
                            InlineComparisonRowState(
                                definition=InlineComparisonRowDefinition('N° Columnas'),
                                first_value=_inspection(reading.columns_operating, COLUMNS_OPERATING_KEY),
                                second_value=_inspection(reading.columns_total, COLUMNS_TOTAL_KEY),
                            )
                        ),
                        className='ada-io-colectiva__columns',
                    ),
                ],
                className='ada-io-colectiva__equipment-section',
            ),
            _state_group('Scavenger (SC1–SC2)', reading.scavengers, 'scavengers'),
        ],
        className='ada-io-colectiva__process',
    )


def _state_group(
    label: str, readings: tuple[ColectivaStateReading, ...], kind: str
) -> Component:
    return html.Section(
        [
            html.H3(label, className='ada-io-colectiva__section-title'),
            html.Div([_state(item) for item in readings],
                     className=f'ada-io-colectiva__states ada-io-colectiva__states--{kind}'),
        ],
        className='ada-io-colectiva__states-section',
    )


# Solo los estados operacionales conocidos generan círculos; lo demás es degradado.
def _state(reading: ColectivaStateReading) -> Component:
    status = reading.state.status
    normalized = (
        reading.state.value.strip().lower()
        if status is DisplayStatus.OK and isinstance(reading.state.value, str)
        else ''
    )
    if status is DisplayStatus.OK and normalized in {'operando', 'detenido'}:
        visual = html.Span(
            className=f'ada-io-colectiva__circle ada-io-colectiva__circle--{normalized}',
            role='img',
            **{'aria-label': normalized.capitalize()},
        )
    else:
        visual = _status_icon(DisplayStatus.INVALID if status is DisplayStatus.OK else status)
    return html.Div(
        [html.Span(reading.definition.label, className='ada-io-colectiva__state-label'), visual],
        className='ada-io-colectiva__state',
        role='button',
        tabIndex=0,
        title=reading.definition.state_kpi_key,
        **{'data-kpi-inspection-key': reading.definition.state_kpi_key},
    )


# La imagen y amperaje son superficies de inspección independientes.
def _equipment(reading: ColectivaEquipmentReading) -> Component:
    definition = reading.definition
    content = [
        html.Div(
            build_equipment_state_image(
                EquipmentStateImage(
                    image=definition.image,
                    state=reading.state,
                    label=definition.label,
                )
            ),
            className='ada-io-colectiva__equipment-image',
            role='button',
            tabIndex=0,
            title=definition.state_kpi_key,
            **{'data-kpi-inspection-key': definition.state_kpi_key},
        ),
    ]
    if definition.amperage_kpi_key is not None and reading.amperage is not None:
        content.append(
            html.Div(
                [
                    html.Span(_display(reading.amperage)),
                    html.Span('A'),
                ],
                className='ada-io-colectiva__amperage',
                role='button',
                tabIndex=0,
                title=definition.amperage_kpi_key,
                **{'data-kpi-inspection-key': definition.amperage_kpi_key},
            )
        )
    return html.Div(content, className='ada-io-colectiva__equipment')


def _inspection(value: DisplayValue, key: str) -> Component:
    return html.Span(
        _display(value),
        role='button',
        tabIndex=0,
        title=key,
        **{'data-kpi-inspection-key': key},
    )


def _status_icon(status: DisplayStatus) -> Component:
    icon = build_display_status_icon(status, class_name='ada-io-colectiva__status-icon')
    if icon is None:
        raise ValueError('Colectiva status icon cannot be resolved')
    return icon


def _display(value: DisplayValue) -> str | Component:
    if value.status is DisplayStatus.OK:
        return str(value.value)
    return _status_icon(value.status)
