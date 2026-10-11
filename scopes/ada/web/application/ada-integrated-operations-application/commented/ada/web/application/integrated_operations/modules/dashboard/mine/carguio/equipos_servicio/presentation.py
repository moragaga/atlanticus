# Presenta Equipos de Servicio desde un único JSON ya resuelto por backend.
from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.kpis.readings import (
    KpiPayloadDataState,
)
from ada.web.ui.display_status import (
    DisplayStatus,
    ValueSeverity,
    build_display_status_icon,
)

from .definitions import EQUIPOS_SERVICIO_KPI_KEY
from .models import (
    EquiposServicioComparison,
    EquiposServicioRow,
    EquiposServicioState,
)

_STATUS_CLASS = {
    ValueSeverity.NEUTRAL: '',
    ValueSeverity.DANGER: 'equipos-servicio__value--danger',
    ValueSeverity.WARNING: 'equipos-servicio__value--warning',
}


def build_equipos_servicio(
    state: EquiposServicioState | None,
    source_status: DisplayStatus,
) -> Component:
    if not isinstance(source_status, DisplayStatus):
        raise TypeError('source_status must be DisplayStatus')

    if state is None:
        return html.Div(
            className='equipos-servicio equipos-servicio--unavailable',
            **{'data-kpi-inspection-key': EQUIPOS_SERVICIO_KPI_KEY},
            children=[
                _build_header(),
                _build_status(source_status, 'Información no disponible'),
            ],
        )

    if not isinstance(state, EquiposServicioState):
        raise TypeError('state must be EquiposServicioState or None')

    if state.data_state is KpiPayloadDataState.ERROR:
        return html.Div(
            className='equipos-servicio equipos-servicio--unavailable',
            **{'data-kpi-inspection-key': EQUIPOS_SERVICIO_KPI_KEY},
            children=[
                _build_header(),
                _build_status(DisplayStatus.INVALID, 'Información no disponible'),
            ],
        )

    children: list[Component] = [
        _build_header(),
        html.Div(
            className='equipos-servicio__rows',
            # Backend define orden, número de equipos y presencia de TOTAL.
            children=[_build_row(row) for row in state.rows],
        ),
    ]
    if state.data_state is KpiPayloadDataState.UNSHIFT:
        children.append(_build_unshift_state())

    # Todo el bloque pertenece al único KPI JSON equipos_servicio.
    return html.Div(
        className='equipos-servicio',
        **{'data-kpi-inspection-key': EQUIPOS_SERVICIO_KPI_KEY},
        children=children,
    )


def _build_header() -> Component:
    # Los encabezados son metadata fija de presentación.
    return html.Div(
        className='equipos-servicio__header',
        children=[
            html.Span(
                'EQUIPO',
                className='equipos-servicio__head equipos-servicio__head--equipo',
            ),
            html.Span('OPERANDO', className='equipos-servicio__head'),
            html.Span('DISPONIBLES', className='equipos-servicio__head'),
            html.Span('F.S', className='equipos-servicio__head'),
        ],
    )


def _build_row(row: EquiposServicioRow) -> Component:
    # is_total sólo modifica presentación; Web no calcula los totales.
    modifier = ' equipos-servicio__row--total' if row.is_total else ''
    return html.Div(
        className=f'equipos-servicio__row{modifier}',
        children=[
            html.Span(
                row.equipo,
                className='equipos-servicio__cell equipos-servicio__cell--equipo',
            ),
            _build_comparison(row.operando),
            _build_comparison(row.disponibles),
            _build_comparison(row.fuera_servicio),
        ],
    )


def _build_comparison(value: EquiposServicioComparison) -> Component:
    status_class = _STATUS_CLASS[value.status]
    real_class = ' '.join(
        item
        for item in ('equipos-servicio__value', status_class)
        if item
    )
    return html.Span(
        className='equipos-servicio__cell equipos-servicio__comparison',
        children=[
            # status aplica sólo a real; plan permanece neutral.
            html.Span(value.real, className=real_class),
            html.Span(' / ', className='equipos-servicio__separator'),
            html.Span(value.plan, className='equipos-servicio__plan'),
        ],
    )


def _build_unshift_state() -> Component:
    return html.Div(
        className='equipos-servicio__state equipos-servicio__state--unshift',
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
        class_name='equipos-servicio__status-icon',
    )
    return html.Div(
        className='equipos-servicio__state equipos-servicio__state--unavailable',
        children=[
            *([] if icon is None else [icon]),
            html.Span(message),
        ],
    )
