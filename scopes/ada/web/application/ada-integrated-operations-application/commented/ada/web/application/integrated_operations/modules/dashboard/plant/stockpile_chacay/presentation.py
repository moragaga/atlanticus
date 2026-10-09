from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon
from ada.web.ui.stockpile import build_stockpile_component

from .definitions import (
    STOCKPILE_CHACAY_PILES,
    STOCKPILE_CHACAY_PILE_POSITIONS,
    STOCKPILE_CHACAY_POSITION_KEY,
    STOCKPILE_CHACAY_POSITIONS,
    STOCKPILE_CHACAY_ROWS,
)
from .models import ChacayMetric, StockpileChacayState


# Toda la composición HTML se mantiene fuera del callback.
def build_stockpile_chacay(state: StockpileChacayState) -> Component:
    if not isinstance(state, StockpileChacayState):
        raise TypeError('state must be StockpileChacayState')
    if len(state.piles) != len(STOCKPILE_CHACAY_PILES):
        raise ValueError('Stockpile Chacay requires exactly four piles')
    if len(state.rows) != len(STOCKPILE_CHACAY_ROWS):
        raise ValueError('Stockpile Chacay requires exactly four metrics')
    return html.Section(
        [
            _position(state.position),
            html.Div(
                [
                    _pile(definition, reading)
                    for definition, reading in zip(STOCKPILE_CHACAY_PILES, state.piles, strict=True)
                ],
                className='ada-io-stockpile-chacay__piles',
            ),
            html.Div(
                [_row(row) for row in state.rows],
                className='ada-io-stockpile-chacay__rows',
            ),
        ],
        className='ada-io-stockpile-chacay',
    )


# Las ocho posiciones comparten un eje: icono, enganche, punto y etiqueta.
# El conector inferior existe en todas las posiciones; las pares continúan hacia las pilas.
# La alineación exacta se define mediante una grilla de ocho columnas y anclajes comunes.
# P2, P4, P6 y P8 son puntos de descarga y usan el icono cargado.
# En posiciones impares se muestra el icono vacío; ambos se orientan desde CSS.
def _position(value: DisplayValue) -> Component:
    active = value.value if value.status is DisplayStatus.OK else None
    children = [
        html.Div(
            [
                html.Span(
                    html.I(
                        className=(
                            'bi bi-minecart-loaded'
                            if number in STOCKPILE_CHACAY_PILE_POSITIONS
                            else 'bi bi-minecart'
                        ),
                        **{'aria-hidden': 'true'},
                    )
                    if active == number else None,
                    className='ada-io-stockpile-chacay__cart',
                ),
                html.Span(className='ada-io-stockpile-chacay__hanger', **{'aria-hidden': 'true'}),
                html.Span(className='ada-io-stockpile-chacay__marker', **{'aria-hidden': 'true'}),
                html.Span(className='ada-io-stockpile-chacay__drop', **{'aria-hidden': 'true'}),
                html.Span(f'P{number}', className='ada-io-stockpile-chacay__position-label'),
                html.Span(
                    className='ada-io-stockpile-chacay__pile-link',
                    **{'aria-hidden': 'true'},
                ),
            ],
            className=(
                'ada-io-stockpile-chacay__position'
                + (
                    ' ada-io-stockpile-chacay__position--pile'
                    if number in STOCKPILE_CHACAY_PILE_POSITIONS else ''
                )
                + (' ada-io-stockpile-chacay__position--active' if active == number else '')
            ),
        )
        for number in STOCKPILE_CHACAY_POSITIONS
    ]
    return html.Div(
        [
            html.Div(children, className='ada-io-stockpile-chacay__track'),
            *([] if value.status is DisplayStatus.OK else [_status(value, 'position')]),
        ],
        className='ada-io-stockpile-chacay__position-section',
        role='button',
        tabIndex=0,
        title=STOCKPILE_CHACAY_POSITION_KEY,
        **{
            'data-kpi-inspection-key': STOCKPILE_CHACAY_POSITION_KEY,
            'aria-label': (
                f'Posición del carro: P{active}'
                if active is not None else 'Posición del carro no disponible'
            ),
        },
    )


# Cada pila se dibuja con el componente común y mantiene su nombre solo como texto alternativo.
def _pile(definition, reading) -> Component:
    return html.Div(
        build_stockpile_component(definition.graphic, reading, alt=f'Pila {definition.label}'),
        className='ada-io-stockpile-chacay__pile',
        role='button',
        tabIndex=0,
        title=definition.kpi_key,
        **{'data-kpi-inspection-key': definition.kpi_key},
    )


# Cada lectura inferior se puede inspeccionar individualmente.
def _row(metric: ChacayMetric) -> Component:
    return html.Div(
        [
            html.Span(metric.label, className='ada-io-stockpile-chacay__row-label'),
            html.Span(
                _display(metric.value),
                className='ada-io-stockpile-chacay__row-value',
                role='button',
                tabIndex=0,
                title=metric.kpi_key,
                **{'data-kpi-inspection-key': metric.kpi_key},
            ),
        ],
        className='ada-io-stockpile-chacay__row',
    )


def _display(value: DisplayValue) -> str | Component:
    if value.status is DisplayStatus.OK:
        return str(value.value)
    return _status(value, 'value')


# Los errores usan la iconografía compartida de ADA.
def _status(value: DisplayValue, kind: str) -> Component:
    icon = build_display_status_icon(
        value.status,
        class_name='ada-io-stockpile-chacay__status-icon',
    )
    if icon is None:
        raise ValueError(f'Stockpile Chacay {kind} status icon cannot be resolved')
    return icon
