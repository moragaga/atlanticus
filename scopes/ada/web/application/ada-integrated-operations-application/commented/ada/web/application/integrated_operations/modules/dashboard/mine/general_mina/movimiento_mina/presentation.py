# Presentación pura de Movimiento Mina. No calcula status ni interpreta los valores del backend.
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

from .models import (
    MOVIMIENTO_MINA_KPI_KEY,
    MovimientoMinaRow,
    MovimientoMinaRowKey,
    MovimientoMinaState,
)

_ROW_LABELS = {
    MovimientoMinaRowKey.EXTRACCION_MINA: 'Ext. Mina Total',
    MovimientoMinaRowKey.REMANEJO: 'Remanejo',
    MovimientoMinaRowKey.MOVIMIENTO_MINA: 'Mov. Mina Total',
    MovimientoMinaRowKey.FASE_9: 'F9',
    MovimientoMinaRowKey.FASE_10: 'F10',
    MovimientoMinaRowKey.FASE_11: 'F11',
    MovimientoMinaRowKey.FASE_12: 'F12',
}

_STATUS_CLASS = {
    DashboardValueStatus.NEUTRAL: '',
    DashboardValueStatus.DANGER: 'movimiento-mina__value--danger',
    DashboardValueStatus.WARNING: 'movimiento-mina__value--warning',
}


def build_movimiento_mina(state: MovimientoMinaState) -> Component:
    if not isinstance(state, MovimientoMinaState):
        raise TypeError('state must be MovimientoMinaState')
    # Todo el bloque representa un único KPI JSON y por eso comparte un solo trigger de inspección.
    if state.data_state is DashboardDataState.ERROR:
        return html.Div(
            className='movimiento-mina movimiento-mina--unavailable',
            **{'data-kpi-inspection-key': MOVIMIENTO_MINA_KPI_KEY},
            children=[
                _build_header(),
                _build_status(
                    status=DisplayStatus.INVALID,
                    message='Información no disponible',
                    modifier='error',
                ),
            ],
        )
    children: list[Component] = [
        _build_header(),
        html.Div(
            className='movimiento-mina__rows',
            children=[_build_row(row) for row in state.rows],
        ),
    ]
    state_component = _build_state(state.data_state)
    if state_component is not None:
        children.append(state_component)
    return html.Div(
        className='movimiento-mina',
        **{'data-kpi-inspection-key': MOVIMIENTO_MINA_KPI_KEY},
        children=children,
    )


def build_movimiento_mina_unavailable(status: DisplayStatus) -> Component:
    if not isinstance(status, DisplayStatus):
        raise TypeError('status must be DisplayStatus')
    # La definición sigue siendo inspeccionable aunque el último valor no esté disponible.
    return html.Div(
        className='movimiento-mina movimiento-mina--unavailable',
        **{'data-kpi-inspection-key': MOVIMIENTO_MINA_KPI_KEY},
        children=[
            _build_header(),
            _build_status(
                status=status,
                message='Información no disponible',
                modifier='unavailable',
            ),
        ],
    )


def _build_header() -> Component:
    return html.Div(
        className='movimiento-mina__header',
        children=[
            _build_header_column('AVANCE', 'Real / Plan acum.'),
            _build_header_column('CIERRE', 'Proy. / Plan día'),
            _build_header_column('RITMO', 'Req./h'),
        ],
    )


def _build_header_column(title: str, subtitle: str) -> Component:
    return html.Div(
        className='movimiento-mina__header-column',
        children=[
            html.Span(title, className='movimiento-mina__header-title'),
            html.Span(subtitle, className='movimiento-mina__header-subtitle'),
        ],
    )


def _build_row(row: MovimientoMinaRow) -> Component:
    return html.Div(
        className='movimiento-mina__row',
        **{'data-movimiento-mina-row': row.key.value},
        children=[
            html.Div(
                f'{_ROW_LABELS[row.key]} (kt)',
                className='movimiento-mina__row-label',
            ),
            html.Div(
                className='movimiento-mina__metrics',
                children=[
                    _build_comparison_metric(
                        row.avance.value,
                        row.avance.plan,
                        row.avance.status,
                    ),
                    _build_comparison_metric(
                        row.cierre.value,
                        row.cierre.plan,
                        row.cierre.status,
                    ),
                    _build_rhythm_metric(row.ritmo),
                ],
            ),
        ],
    )


def _build_comparison_metric(
    value: object,
    plan: object,
    status: DashboardValueStatus,
) -> Component:
    modifier = _STATUS_CLASS[status]
    value_class = ' '.join(
        item
        for item in ('movimiento-mina__value', modifier)
        if item
    )
    return html.Div(
        className='movimiento-mina__metric',
        children=[
            html.Span(value, className=value_class),
            html.Span('/', className='movimiento-mina__separator'),
            html.Span(plan, className='movimiento-mina__plan'),
        ],
    )


def _build_rhythm_metric(value: object) -> Component:
    return html.Div(
        className='movimiento-mina__metric',
        children=[
            html.Span(value, className='movimiento-mina__value'),
            html.Span('/h', className='movimiento-mina__unit'),
        ],
    )


def _build_state(state: DashboardDataState) -> Component | None:
    if state is DashboardDataState.OK:
        return None
    if state is DashboardDataState.UNSHIFT:
        return html.Div(
            className='movimiento-mina__state movimiento-mina__state--unshift',
            children=[
                html.I(
                    className='bi bi-hourglass-split',
                    **{'aria-hidden': 'true'},
                ),
                html.Span(
                    'Datos del turno aún no disponibles',
                    className='movimiento-mina__state-message',
                ),
            ],
        )
    return None


def _build_status(
    *,
    status: DisplayStatus,
    message: str,
    modifier: str,
) -> Component:
    icon = build_display_status_icon(
        status,
        class_name='movimiento-mina__state-icon',
    )
    return html.Div(
        className=f'movimiento-mina__state movimiento-mina__state--{modifier}',
        children=[
            *([] if icon is None else [icon]),
            html.Span(message, className='movimiento-mina__state-message'),
        ],
    )
