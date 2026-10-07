# MP10 presenta dos filas independientes provenientes directamente de API, sin semántica de turno.
from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)
from ada.web.ui.display_status import DisplayStatus, build_display_status_icon

from .definitions import (
    MP10_HOTEL_MINA_INST_KPI_KEY,
    MP10_HOTEL_MINA_LABEL,
    MP10_HOTEL_MINA_PROY_KPI_KEY,
    MP10_HOTEL_MINA_PROY_LABEL,
    MP10_UNIT,
)
from .models import MP10MetricState, MP10State

_ALERT_CLASS = {
    DashboardValueStatus.NEUTRAL: 'mp10__alert--neutral',
    DashboardValueStatus.DANGER: 'mp10__alert--danger',
    DashboardValueStatus.WARNING: 'mp10__alert--warning',
}


def build_mp10(state: MP10State) -> Component:
    if not isinstance(state, MP10State):
        raise TypeError('state must be MP10State')
    return html.Div(
        className='mp10',
        children=[
            _build_row(
                label=MP10_HOTEL_MINA_LABEL,
                unit=MP10_UNIT,
                metric=state.instant,
                source_status=state.instant_status,
                kpi_key=MP10_HOTEL_MINA_INST_KPI_KEY,
            ),
            _build_row(
                label=MP10_HOTEL_MINA_PROY_LABEL,
                unit=MP10_UNIT,
                metric=state.projection,
                source_status=state.projection_status,
                kpi_key=MP10_HOTEL_MINA_PROY_KPI_KEY,
            ),
        ],
    )


def _build_row(
    *,
    label: str,
    unit: str,
    metric: MP10MetricState | None,
    source_status: DisplayStatus,
    kpi_key: str,
) -> Component:
    return html.Div(
        className='mp10__row',
        children=[
            # Label y unidad siguen la misma lectura visual usada por Stock 3080.
            html.Div(
                className='mp10__descriptor',
                children=[
                    html.Span(label, className='mp10__label'),
                    html.Span(f'({unit})', className='mp10__unit'),
                ],
            ),
            html.Div(
                className='mp10__result',
                children=[
                    # La inspección pertenece sólo al valor, igual que Stock 3080.
                    html.Span(
                        _build_value(metric, source_status),
                        className='mp10__value',
                        **{'data-kpi-inspection-key': kpi_key},
                    ),
                    _build_alert(metric),
                ],
            ),
        ],
    )


def _build_value(
    metric: MP10MetricState | None,
    source_status: DisplayStatus,
) -> str | Component:
    if metric is not None:
        return str(metric.value)
    # El estado del collector reemplaza el valor cuando el JSON no está disponible.
    icon = build_display_status_icon(
        source_status,
        class_name='mp10__status-icon',
    )
    if icon is not None:
        return icon
    return '-'


def _build_alert(metric: MP10MetricState | None) -> Component | None:
    if metric is None or metric.alert is None:
        return None
    # El backend ya decidió texto y severidad; Web sólo aplica su representación.
    return html.Span(
        metric.alert,
        className=f'mp10__alert {_ALERT_CLASS[metric.status]}',
    )
