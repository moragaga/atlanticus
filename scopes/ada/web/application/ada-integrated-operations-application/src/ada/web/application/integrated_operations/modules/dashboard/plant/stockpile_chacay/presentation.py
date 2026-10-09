from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon
from ada.web.ui.stockpile import build_stockpile_component

from .definitions import (
    STOCKPILE_CHACAY_PILE_POSITIONS,
    STOCKPILE_CHACAY_PILES,
    STOCKPILE_CHACAY_POSITION_KEY,
    STOCKPILE_CHACAY_POSITIONS,
    STOCKPILE_CHACAY_ROWS,
)
from .feeders import build_chacay_feeders
from .models import ChacayMetric, StockpileChacayState


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
            build_chacay_feeders(state.feeders),
            html.Div(
                [_row(row) for row in state.rows],
                className='ada-io-stockpile-chacay__rows',
            ),
        ],
        className='ada-io-stockpile-chacay',
    )


def _position(value: DisplayValue) -> Component:
    active = value.value if value.status is DisplayStatus.OK else 1
    positions = [_position_item(value, active, number) for number in STOCKPILE_CHACAY_POSITIONS]
    label = (
        f'Posición del carro: P{active}'
        if value.status is DisplayStatus.OK
        else 'Posición no disponible; indicador de estado en P1'
    )
    return html.Div(
        html.Div(positions, className='ada-io-stockpile-chacay__track'),
        className='ada-io-stockpile-chacay__position-section',
        role='button',
        tabIndex=0,
        title=STOCKPILE_CHACAY_POSITION_KEY,
        **{
            'data-kpi-inspection-key': STOCKPILE_CHACAY_POSITION_KEY,
            'aria-label': label,
        },
    )


def _position_item(value: DisplayValue, active: int, number: int) -> Component:
    upper = _upper_content(value, active, number)
    lower = _lower_content(active, number)
    classes = ['ada-io-stockpile-chacay__position']
    if number in STOCKPILE_CHACAY_PILE_POSITIONS:
        classes.append('ada-io-stockpile-chacay__position--pile')
    if active == number:
        classes.append('ada-io-stockpile-chacay__position--active')
    if value.status is DisplayStatus.OK and active == number and number % 2 == 0:
        classes.append('ada-io-stockpile-chacay__position--unloading')
    return html.Div(
        [
            html.Span(
                upper,
                className='ada-io-stockpile-chacay__cart ada-io-stockpile-chacay__cart--upper',
            ),
            html.Span(className='ada-io-stockpile-chacay__marker', **{'aria-hidden': 'true'}),
            html.Span(className='ada-io-stockpile-chacay__drop', **{'aria-hidden': 'true'}),
            html.Span(f'P{number}', className='ada-io-stockpile-chacay__position-label'),
            html.Span(
                className='ada-io-stockpile-chacay__lower-connector',
                **{'aria-hidden': 'true'},
            ),
            html.Span(
                lower,
                className='ada-io-stockpile-chacay__cart ada-io-stockpile-chacay__cart--lower',
            ),
        ],
        className=' '.join(classes),
    )


def _upper_content(value: DisplayValue, active: int, number: int) -> Component | None:
    if active != number or number % 2 == 0:
        return None
    if value.status is not DisplayStatus.OK:
        return _status(value, 'position')
    return html.I(className='bi bi-minecart', **{'aria-hidden': 'true'})


def _lower_content(active: int, number: int) -> Component | None:
    if active != number or number % 2:
        return None
    return html.I(className='bi bi-minecart-loaded', **{'aria-hidden': 'true'})


def _pile(definition, reading) -> Component:
    return html.Div(
        build_stockpile_component(definition.graphic, reading, alt=f'Pila {definition.label}'),
        className='ada-io-stockpile-chacay__pile',
        role='button',
        tabIndex=0,
        title=definition.kpi_key,
        **{'data-kpi-inspection-key': definition.kpi_key},
    )


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


def _status(value: DisplayValue, kind: str) -> Component:
    icon = build_display_status_icon(
        value.status,
        class_name='ada-io-stockpile-chacay__status-icon',
    )
    if icon is None:
        raise ValueError(f'Stockpile Chacay {kind} status icon cannot be resolved')
    return icon
