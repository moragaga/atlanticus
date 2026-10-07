from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.data_state import (
    DashboardDataState,
)
from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)
from ada.web.ui.display_status import DisplayStatus, build_display_status_icon

from .definitions import CARGUIO_GLOBAL_TURNO_KPI_KEY
from .models import (
    CarguioGlobalTurnoComparison,
    CarguioGlobalTurnoRow,
    CarguioGlobalTurnoState,
)

_STATUS_CLASS = {
    DashboardValueStatus.NEUTRAL: '',
    DashboardValueStatus.DANGER: 'carguio-global-turno__value--danger',
    DashboardValueStatus.WARNING: 'carguio-global-turno__value--warning',
}


def build_carguio_global_turno(
    state: CarguioGlobalTurnoState | None,
    source_status: DisplayStatus,
) -> Component:
    if not isinstance(source_status, DisplayStatus):
        raise TypeError('source_status must be DisplayStatus')

    if state is None:
        return html.Div(
            className='carguio-global-turno carguio-global-turno--unavailable',
            **{'data-kpi-inspection-key': CARGUIO_GLOBAL_TURNO_KPI_KEY},
            children=[
                _build_header(),
                _build_status(source_status, 'Información no disponible'),
            ],
        )

    if not isinstance(state, CarguioGlobalTurnoState):
        raise TypeError('state must be CarguioGlobalTurnoState or None')

    if state.data_state is DashboardDataState.ERROR:
        return html.Div(
            className='carguio-global-turno carguio-global-turno--unavailable',
            **{'data-kpi-inspection-key': CARGUIO_GLOBAL_TURNO_KPI_KEY},
            children=[
                _build_header(),
                _build_status(DisplayStatus.INVALID, 'Información no disponible'),
            ],
        )

    children: list[Component] = [
        _build_header(),
        html.Div(
            className='carguio-global-turno__rows',
            children=[_build_row(row) for row in state.rows],
        ),
    ]
    if state.data_state is DashboardDataState.UNSHIFT:
        children.append(_build_unshift_state())

    return html.Div(
        className='carguio-global-turno',
        **{'data-kpi-inspection-key': CARGUIO_GLOBAL_TURNO_KPI_KEY},
        children=children,
    )


def _build_header() -> Component:
    return html.Div(
        className='carguio-global-turno__header',
        children=[
            html.Span(
                'FLOTA',
                className='carguio-global-turno__head carguio-global-turno__head--flota',
            ),
            html.Span('OP / REQ', className='carguio-global-turno__head'),
            html.Span('DISP. (%)', className='carguio-global-turno__head'),
            html.Span('UEBD (%)', className='carguio-global-turno__head'),
            html.Span('REND. (kt/h)', className='carguio-global-turno__head'),
        ],
    )


def _build_row(row: CarguioGlobalTurnoRow) -> Component:
    modifier = ' carguio-global-turno__row--total' if row.is_total else ''
    return html.Div(
        className=f'carguio-global-turno__row{modifier}',
        children=[
            html.Span(
                row.flota,
                className='carguio-global-turno__cell carguio-global-turno__cell--flota',
            ),
            _build_comparison(row.op_req),
            _build_comparison(row.disponibilidad),
            _build_comparison(row.uebd),
            _build_comparison(row.rendimiento),
        ],
    )


def _build_comparison(value: CarguioGlobalTurnoComparison) -> Component:
    status_class = _STATUS_CLASS[value.status]
    real_class = ' '.join(
        item
        for item in ('carguio-global-turno__value', status_class)
        if item
    )
    return html.Span(
        className='carguio-global-turno__cell carguio-global-turno__comparison',
        children=[
            html.Span(value.real, className=real_class),
            html.Span(' / ', className='carguio-global-turno__separator'),
            html.Span(value.plan, className='carguio-global-turno__plan'),
        ],
    )


def _build_unshift_state() -> Component:
    return html.Div(
        className='carguio-global-turno__state carguio-global-turno__state--unshift',
        children=[
            html.I(
                className='bi bi-hourglass-split',
                **{'aria-hidden': 'true'},
            ),
            html.Span('Datos del turno aún no disponibles'),
        ],
    )


def _build_status(status: DisplayStatus, message: str) -> Component:
    icon = build_display_status_icon(
        status,
        class_name='carguio-global-turno__status-icon',
    )
    return html.Div(
        className='carguio-global-turno__state carguio-global-turno__state--unavailable',
        children=[
            *([] if icon is None else [icon]),
            html.Span(message),
        ],
    )
