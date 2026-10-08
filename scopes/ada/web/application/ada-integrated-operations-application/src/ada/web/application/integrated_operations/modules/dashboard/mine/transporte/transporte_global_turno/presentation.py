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
from atlanticus.web.inline_comparison_row import (
    InlineComparisonRowState,
    build_inline_comparison_row,
)
from atlanticus.web.inline_value_row import InlineValueRowTone

from .definitions import (
    TRANSPORTE_GLOBAL_TURNO_KPI_KEY,
    TRANSPORTE_GLOBAL_TURNO_ROW_DEFINITIONS,
)
from .models import TransporteGlobalTurnoRow, TransporteGlobalTurnoState

_TONE = {
    DashboardValueStatus.NEUTRAL: InlineValueRowTone.DEFAULT,
    DashboardValueStatus.DANGER: InlineValueRowTone.DANGER,
    DashboardValueStatus.WARNING: InlineValueRowTone.WARNING,
}


def build_transporte_global_turno(
    state: TransporteGlobalTurnoState | None,
    source_status: DisplayStatus,
) -> Component:
    if not isinstance(source_status, DisplayStatus):
        raise TypeError('source_status must be DisplayStatus')

    if state is None:
        return _build_root(
            [
                _build_status(source_status, 'Información no disponible'),
            ]
        )

    if not isinstance(state, TransporteGlobalTurnoState):
        raise TypeError('state must be TransporteGlobalTurnoState or None')

    if state.data_state is DashboardDataState.ERROR:
        return _build_root(
            [
                _build_status(DisplayStatus.INVALID, 'Información no disponible'),
            ]
        )

    if state.data_state is DashboardDataState.UNSHIFT:
        return _build_root([_build_unshift_state()])

    return _build_root(
        [
            html.Div(
                className='transporte-global-turno__rows',
                children=[
                    _build_row(row=row)
                    for index, row in enumerate(state.rows)
                ],
            )
        ]
    )


def _build_root(children: list[Component]) -> Component:
    return html.Div(
        className='transporte-global-turno',
        **{'data-kpi-inspection-key': TRANSPORTE_GLOBAL_TURNO_KPI_KEY},
        children=children,
    )


def _build_row(
    *,
    row: TransporteGlobalTurnoRow,
) -> Component:
    return build_inline_comparison_row(
        InlineComparisonRowState(
            definition=TRANSPORTE_GLOBAL_TURNO_ROW_DEFINITIONS[row.key],
            first_value=row.real.value,
            second_value=row.plan.value,
            first_tone=_TONE[row.real.status],
            second_tone=_TONE[row.plan.status],
        )
    )


def _build_unshift_state() -> Component:
    return html.Div(
        className='transporte-global-turno__state transporte-global-turno__state--unshift',
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
        class_name='transporte-global-turno__status-icon',
    )
    return html.Div(
        className='transporte-global-turno__state transporte-global-turno__state--unavailable',
        children=[
            *([] if icon is None else [icon]),
            html.Span(message),
        ],
    )
