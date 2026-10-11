# Presentación específica de Perforación: resumen semanal y detalle jerárquico comparten una card.
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

from .definitions import PERFORACION_DETALLE_KPI_KEY, PERFORACION_RESUMEN_KPI_KEY
from .models import (
    PerforacionComparison,
    PerforacionDetalleState,
    PerforacionEquipoState,
    PerforacionFaseState,
    PerforacionResumenState,
    PerforacionState,
)

_STATUS_CLASS = {
    ValueSeverity.NEUTRAL: '',
    ValueSeverity.DANGER: 'perforacion__value--danger',
    ValueSeverity.WARNING: 'perforacion__value--warning',
}


def build_perforacion(state: PerforacionState) -> Component:
    if not isinstance(state, PerforacionState):
        raise TypeError('state must be PerforacionState')
    return html.Div(
        className='perforacion',
        children=[
            # Cada JSON conserva su propio estado y puede degradarse sin ocultar al otro.
            _build_resumen(state.resumen, state.resumen_status),
            _build_detalle(state.detalle, state.detalle_status),
        ],
    )


# El resumen completo representa perforacion_resumen y abre una sola definición.
def _build_resumen(
    state: PerforacionResumenState | None,
    status: DisplayStatus,
) -> Component:
    if state is None:
        return html.Div(
            className='perforacion__resumen perforacion__resumen--unavailable',
            **{'data-kpi-inspection-key': PERFORACION_RESUMEN_KPI_KEY},
            children=[
                _build_resumen_title(),
                _build_status(status, 'Información no disponible'),
            ],
        )
    if state.data_state is KpiPayloadDataState.ERROR:
        return html.Div(
            className='perforacion__resumen perforacion__resumen--unavailable',
            **{'data-kpi-inspection-key': PERFORACION_RESUMEN_KPI_KEY},
            children=[
                _build_resumen_title(),
                _build_status(DisplayStatus.INVALID, 'Información no disponible'),
            ],
        )

    acumulado = state.acumulado_semanal
    if acumulado is None:
        raise ValueError('Perforacion resumen acumulado_semanal is required')

    children: list[Component] = [
        _build_resumen_title(),
        # El porcentaje llega listo desde backend y sólo gobierna el ancho visual del fill.
        _build_progress(state.avance, acumulado.status),
        html.Div(
            className='perforacion__summary-metrics',
            children=[
                html.Div(
                    className='perforacion__summary-item',
                    children=[
                        html.Span(
                            'Acum. semanal',
                            className='perforacion__summary-label',
                        ),
                        _build_comparison(acumulado),
                    ],
                ),
                html.Div(
                    className='perforacion__summary-item perforacion__summary-item--plan',
                    children=[
                        html.Span('PS', className='perforacion__summary-label'),
                        html.Span(
                            state.plan_semanal,
                            className='perforacion__summary-plan',
                        ),
                    ],
                ),
            ],
        ),
    ]
    if state.data_state is KpiPayloadDataState.UNSHIFT:
        children.append(_build_unshift_state())

    return html.Div(
        className='perforacion__resumen',
        **{'data-kpi-inspection-key': PERFORACION_RESUMEN_KPI_KEY},
        children=children,
    )


def _build_resumen_title() -> Component:
    return html.Div(
        'AVANCE SEMANAL (m)',
        className='perforacion__summary-title',
    )


def _build_progress(
    avance: str | None,
    status: ValueSeverity,
) -> Component:
    fill = None
    if avance is not None:
        modifier = _STATUS_CLASS[status]
        # La propiedad dinámica es estrictamente presentación; no se calcula ni castea aquí.
        fill = html.Div(
            className=' '.join(
                item
                for item in ('perforacion__progress-fill', modifier)
                if item
            ),
            style={'width': avance},
        )
    return html.Div(
        className='perforacion__progress',
        children=[] if fill is None else [fill],
    )


# La tabla completa representa perforacion_detalle; fases y filas no son KPI independientes.
def _build_detalle(
    state: PerforacionDetalleState | None,
    status: DisplayStatus,
) -> Component:
    if state is None:
        return html.Div(
            className='perforacion__detalle perforacion__detalle--unavailable',
            **{'data-kpi-inspection-key': PERFORACION_DETALLE_KPI_KEY},
            children=[
                _build_table_header_only(),
                _build_status(status, 'Información no disponible'),
            ],
        )
    if state.data_state is KpiPayloadDataState.ERROR:
        return html.Div(
            className='perforacion__detalle perforacion__detalle--unavailable',
            **{'data-kpi-inspection-key': PERFORACION_DETALLE_KPI_KEY},
            children=[
                _build_table_header_only(),
                _build_status(DisplayStatus.INVALID, 'Información no disponible'),
            ],
        )

    children: list[Component] = [
        html.Table(
            className='perforacion__table',
            children=[
                _build_table_head(),
                html.Tbody(
                    children=[
                        row
                        for fase in state.fases
                        for row in _build_fase_rows(fase)
                    ],
                ),
            ],
        )
    ]
    if state.data_state is KpiPayloadDataState.UNSHIFT:
        children.append(_build_unshift_state())

    return html.Div(
        className='perforacion__detalle',
        **{'data-kpi-inspection-key': PERFORACION_DETALLE_KPI_KEY},
        children=children,
    )


def _build_table_header_only() -> Component:
    return html.Table(
        className='perforacion__table perforacion__table--header-only',
        children=[_build_table_head()],
    )


def _build_table_head() -> Component:
    return html.Thead(
        children=[
            html.Tr(
                children=[
                    html.Th('FASE', className='perforacion__head perforacion__head--fase'),
                    html.Th(
                        'PERFORADORA',
                        className='perforacion__head perforacion__head--equipo',
                    ),
                    html.Th(
                        'DÍA ANTERIOR (m)',
                        className='perforacion__head',
                    ),
                    html.Th(
                        'ACUM. SEMANA (m)',
                        className='perforacion__head',
                    ),
                ],
            )
        ]
    )


def _build_fase_rows(fase: PerforacionFaseState) -> list[Component]:
    rows: list[Component] = []
    row_span = len(fase.perforadoras)
    # La fase se representa una sola vez con rowSpan y la cantidad real de perforadoras recibidas.
    for index, equipo in enumerate(fase.perforadoras):
        cells: list[Component] = []
        if index == 0:
            cells.append(
                html.Td(
                    fase.fase,
                    rowSpan=max(row_span, 1),
                    className='perforacion__cell perforacion__cell--fase',
                )
            )
        cells.extend(_build_equipo_cells(equipo))
        rows.append(html.Tr(children=cells))
    return rows


def _build_equipo_cells(equipo: PerforacionEquipoState) -> list[Component]:
    return [
        html.Td(
            equipo.perforadora,
            className='perforacion__cell perforacion__cell--equipo',
        ),
        html.Td(
            _build_comparison(equipo.dia_anterior),
            className='perforacion__cell perforacion__cell--metric',
        ),
        html.Td(
            _build_comparison(equipo.acumulado_semanal),
            className='perforacion__cell perforacion__cell--metric',
        ),
    ]


def _build_comparison(value: PerforacionComparison) -> Component:
    modifier = _STATUS_CLASS[value.status]
    real_class = ' '.join(
        item for item in ('perforacion__value', modifier) if item
    )
    return html.Span(
        className='perforacion__comparison',
        children=[
            # Sólo el real recibe status; plan permanece neutral.
            html.Span(value.real, className=real_class),
            html.Span(' / ', className='perforacion__separator'),
            html.Span(value.plan, className='perforacion__plan'),
        ],
    )


def _build_unshift_state() -> Component:
    return html.Div(
        className='perforacion__state perforacion__state--unshift',
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
        class_name='perforacion__status-icon',
    )
    return html.Div(
        className='perforacion__state perforacion__state--unavailable',
        children=[
            *([] if icon is None else [icon]),
            html.Span(message, className='perforacion__state-message'),
        ],
    )
