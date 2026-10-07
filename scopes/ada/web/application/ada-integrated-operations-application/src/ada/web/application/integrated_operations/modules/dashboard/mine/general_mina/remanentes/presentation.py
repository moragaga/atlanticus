from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.data_state import (
    DashboardDataState,
)
from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)
from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon
from atlanticus.web.inline_value_row import (
    InlineValueRowState,
    InlineValueRowTone,
    build_inline_value_row,
)

from .definitions import STOCK_3080_ROW_DEFINITION
from .models import RemanentesState, RemanentesSummaryRow, RemanentesSummaryState

_TONE = {
    DashboardValueStatus.NEUTRAL: InlineValueRowTone.DEFAULT,
    DashboardValueStatus.DANGER: InlineValueRowTone.DANGER,
    DashboardValueStatus.WARNING: InlineValueRowTone.WARNING,
}


def build_remanentes(state: RemanentesState) -> Component:
    if not isinstance(state, RemanentesState):
        raise TypeError('state must be RemanentesState')
    return html.Div(
        className='remanentes',
        children=[
            _build_summary(state.summary, state.summary_status),
            html.Div(
                className='remanentes__metrics',
                children=[
                    build_inline_value_row(
                        InlineValueRowState(
                            definition=STOCK_3080_ROW_DEFINITION,
                            value=_build_display_value(state.stock_3080.value),
                            tone=_TONE[state.stock_3080.status],
                        )
                    )
                ],
            ),
        ],
    )


def _build_summary(
    state: RemanentesSummaryState | None,
    status: DisplayStatus,
) -> Component:
    if state is None:
        return html.Div(
            className='remanentes__summary remanentes__summary--unavailable',
            children=[
                _build_header(),
                _build_status(status, 'Información no disponible'),
            ],
        )
    if state.data_state is DashboardDataState.ERROR:
        return html.Div(
            className='remanentes__summary remanentes__summary--error',
            children=[
                _build_header(),
                _build_status(DisplayStatus.INVALID, 'Información no disponible'),
            ],
        )
    children: list[Component] = [
        _build_header(),
        html.Div(
            className='remanentes__rows',
            children=[_build_row(row) for row in state.rows],
        ),
    ]
    if state.data_state is DashboardDataState.UNSHIFT:
        children.append(
            html.Div(
                className='remanentes__state remanentes__state--unshift',
                children=['Datos del turno aún no disponibles'],
            )
        )
    return html.Div(
        className='remanentes__summary',
        children=children,
    )


def _build_header() -> Component:
    return html.Div(
        className='remanentes__header',
        children=[
            html.Span('', className='remanentes__header-cell remanentes__header-cell--fase'),
            html.Span('MINERAL', className='remanentes__header-cell'),
            html.Span('ESTERIL', className='remanentes__header-cell'),
            html.Span('B. LEY', className='remanentes__header-cell'),
            html.Span('TOT', className='remanentes__header-cell'),
        ],
    )


def _build_row(row: RemanentesSummaryRow) -> Component:
    return html.Div(
        className='remanentes__row',
        children=[
            html.Span(row.fase, className='remanentes__cell remanentes__cell--fase'),
            html.Span(row.mineral, className='remanentes__cell'),
            html.Span(row.esteril, className='remanentes__cell'),
            html.Span(row.baja_ley, className='remanentes__cell'),
            html.Span(row.total, className='remanentes__cell'),
        ],
    )


def _build_status(status: DisplayStatus, message: str) -> Component:
    icon = build_display_status_icon(
        status,
        class_name='remanentes__status-icon',
    )
    return html.Div(
        className='remanentes__state remanentes__state--unavailable',
        children=[
            *([] if icon is None else [icon]),
            html.Span(message, className='remanentes__state-message'),
        ],
    )


def _build_display_value(value: DisplayValue) -> str | Component:
    if value.status is DisplayStatus.OK:
        if isinstance(value.value, Component):
            return value.value
        return str(value.value)
    icon = build_display_status_icon(
        value.status,
        class_name='remanentes__inline-status-icon',
    )
    if icon is not None:
        return icon
    return '-'
