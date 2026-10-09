from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon

from .models import LeyesMetric, LeyesRow, LeyesState


def build_leyes_summary(state: LeyesState) -> Component:
    if not isinstance(state, LeyesState):
        raise TypeError('state must be LeyesState')
    return html.Section(
        [
            html.H3('LEYES', className='ada-io-leyes__title'),
            html.Div(
                html.Table(
                    [
                        html.Thead(html.Tr([
                            _header('', first=True),
                            _header('HORA'),
                            _header('TURNO'),
                            _header('DÍA'),
                            _header('PLAN'),
                        ])),
                        html.Tbody([_row(row) for row in state.rows]),
                    ],
                    className='ada-io-leyes__table',
                ),
                className='ada-io-leyes__viewport',
            ),
        ],
        className='ada-io-leyes',
    )


def _header(label: str, *, first: bool = False) -> Component:
    class_name = 'ada-io-leyes__head'
    class_name += ' ada-io-leyes__head--name' if first else ' ada-io-leyes__head--period'
    return html.Th(label, scope='col', className=class_name)


def _row(row: LeyesRow) -> Component:
    return html.Tr(
        [
            html.Th(
                html.Span(row.label, title=row.label, className='ada-io-leyes__label'),
                scope='row',
                className='ada-io-leyes__row-header',
            ),
            _cell(row.hora),
            _cell(row.turno),
            _cell(row.dia),
            _cell(row.plan),
        ],
        **{'data-leyes-row': row.key},
    )


def _cell(metric: LeyesMetric) -> Component:
    return html.Td(
        html.Span(
            _display(metric.value),
            className='ada-io-leyes__value',
            role='button',
            tabIndex=0,
            title=metric.kpi_key,
            **{'data-kpi-inspection-key': metric.kpi_key},
        ),
        className='ada-io-leyes__cell',
    )


def _display(value: DisplayValue) -> str | Component:
    if value.status is DisplayStatus.OK:
        return str(value.value)
    icon = build_display_status_icon(value.status)
    if icon is None:
        raise ValueError('Leyes status icon cannot be resolved')
    return icon
