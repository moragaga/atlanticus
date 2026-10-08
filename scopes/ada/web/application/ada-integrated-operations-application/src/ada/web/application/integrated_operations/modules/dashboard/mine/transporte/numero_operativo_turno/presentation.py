from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.data_state import (
    DashboardDataState,
)
from ada.web.ui.display_status import DisplayStatus, build_display_status_icon
from atlanticus.web.inline_value_row import (
    InlineValueRowState,
    build_inline_value_row,
)

from .definitions import (
    NUMERO_OPERATIVO_TURNO_DEFINITIONS,
    NUMERO_OPERATIVO_TURNO_KPI_KEY,
)
from .models import NumeroOperativoTurnoState


def build_numero_operativo_turno(
    state: NumeroOperativoTurnoState | None,
    source_status: DisplayStatus,
) -> Component:
    if not isinstance(source_status, DisplayStatus):
        raise TypeError('source_status must be DisplayStatus')

    if state is None:
        return _build_root(
            [_build_status(source_status, 'Información no disponible')]
        )

    if not isinstance(state, NumeroOperativoTurnoState):
        raise TypeError('state must be NumeroOperativoTurnoState or None')

    if state.data_state is DashboardDataState.ERROR:
        return _build_root(
            [_build_status(DisplayStatus.INVALID, 'Información no disponible')]
        )

    if state.data_state is DashboardDataState.UNSHIFT:
        return _build_root([_build_unshift_state()])

    values = state.as_mapping()
    items = tuple(values.items())
    return _build_root(
        [
            html.Div(
                className='numero-operativo-turno__rows',
                children=[
                    build_inline_value_row(
                        InlineValueRowState(
                            definition=NUMERO_OPERATIVO_TURNO_DEFINITIONS[key],
                            value=value,
                        )
                    )
                    for index, (key, value) in enumerate(items)
                ],
            )
        ]
    )


def _build_root(children: list[Component]) -> Component:
    return html.Div(
        className='numero-operativo-turno',
        **{'data-kpi-inspection-key': NUMERO_OPERATIVO_TURNO_KPI_KEY},
        children=children,
    )


def _build_unshift_state() -> Component:
    return html.Div(
        className='numero-operativo-turno__state numero-operativo-turno__state--unshift',
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
        class_name='numero-operativo-turno__status-icon',
    )
    return html.Div(
        className='numero-operativo-turno__state numero-operativo-turno__state--unavailable',
        children=[
            *([] if icon is None else [icon]),
            html.Span(message),
        ],
    )
