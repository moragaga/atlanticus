# Presenta Gestión Carguío • Turno desde secciones explícitas, sin inferir spans desde filas vacías.
from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.kpis.readings import (
    KpiPayloadDataState,
)
from ada.web.ui.display_status import DisplayStatus, build_display_status_icon

from .definitions import GESTION_CARGUIO_TURNO_KPI_KEY
from .models import (
    GestionCarguioTurnoRow,
    GestionCarguioTurnoSection,
    GestionCarguioTurnoState,
)

_COLUMN_COUNT = 8


def build_gestion_carguio_turno(
    state: GestionCarguioTurnoState | None,
    source_status: DisplayStatus,
) -> Component:
    if not isinstance(source_status, DisplayStatus):
        raise TypeError('source_status must be DisplayStatus')

    if state is None:
        return _build_root(
            [
                _build_table(()),
                _build_status(source_status, 'Información no disponible'),
            ]
        )

    if not isinstance(state, GestionCarguioTurnoState):
        raise TypeError('state must be GestionCarguioTurnoState or None')

    if state.data_state is KpiPayloadDataState.ERROR:
        return _build_root(
            [
                _build_table(()),
                _build_status(DisplayStatus.INVALID, 'Información no disponible'),
            ]
        )

    if state.data_state is KpiPayloadDataState.UNSHIFT:
        return _build_root(
            [
                _build_table(()),
                _build_unshift_state(),
            ]
        )

    # Sólo OK dibuja secciones y leyenda operacional.
    return _build_root(
        [
            _build_table(state.sections),
            _build_legend(),
        ]
    )


def _build_root(children: list[Component]) -> Component:
    # La card completa corresponde al único KPI JSON gestion_carguio_turno.
    return html.Div(
        className='gestion-carguio-turno',
        **{'data-kpi-inspection-key': GESTION_CARGUIO_TURNO_KPI_KEY},
        children=children,
    )


def _build_table(
    sections: tuple[GestionCarguioTurnoSection, ...],
) -> Component:
    rows: list[Component] = []
    for section in sections:
        # Cada sección crea el span categórico y luego preserva el orden de sus equipos.
        rows.append(_build_section_row(section))
        rows.extend(_build_data_row(row) for row in section.rows)

    return html.Div(
        className='gestion-carguio-turno__table-wrapper',
        children=[
            html.Table(
                className='gestion-carguio-turno__table',
                children=[
                    html.Thead(
                        html.Tr(
                            [
                                _build_head('', 'equipo'),
                                _build_head('FASE', 'fase'),
                                _build_head('UEBD (%)', 'uebd'),
                                _build_head('Disponibilidad (%)', 'disponibilidad'),
                                _build_head('Rendimiento (t/hr)', 'rendimiento'),
                                _build_head('T.Cola (min)', 'cola'),
                                _build_head('Estado', 'estado'),
                                _build_head('Razón', 'razon'),
                            ]
                        )
                    ),
                    html.Tbody(rows),
                ],
            )
        ],
    )


def _build_head(label: str, modifier: str) -> Component:
    return html.Th(
        label,
        className=f'gestion-carguio-turno__head gestion-carguio-turno__head--{modifier}',
        scope='col',
    )


def _build_section_row(section: GestionCarguioTurnoSection) -> Component:
    # El span es presentación directa de section.label; no se infiere desde nulls.
    return html.Tr(
        className='gestion-carguio-turno__section-row',
        children=[
            html.Th(
                section.label,
                colSpan=_COLUMN_COUNT,
                scope='rowgroup',
                className='gestion-carguio-turno__section',
            )
        ],
    )


def _build_data_row(row: GestionCarguioTurnoRow) -> Component:
    return html.Tr(
        className='gestion-carguio-turno__row',
        children=[
            _build_cell(row.equipo, 'equipo'),
            _build_cell(row.fase, 'fase'),
            _build_cell(row.uebd_pct, 'uebd'),
            _build_cell(row.disponibilidad_fisica_pct, 'disponibilidad'),
            _build_cell(row.rendimiento_efectivo_tph, 'rendimiento'),
            _build_cell(row.cola_pala_min, 'cola'),
            _build_cell(row.estado, 'estado'),
            _build_cell(row.razon, 'razon'),
        ],
    )


def _build_cell(value: object, modifier: str) -> Component:
    # El valor se presenta tal como llega; no hay casting, redondeo ni normalización.
    return html.Td(
        value,
        className=f'gestion-carguio-turno__cell gestion-carguio-turno__cell--{modifier}',
    )


def _build_legend() -> Component:
    # La semántica E/D/R/M es metadata fija de esta presentación.
    return html.Div(
        className='gestion-carguio-turno__legend',
        children=[
            html.Span('E • Efectivo'),
            html.Span('D • Demora'),
            html.Span('R • Reserva'),
            html.Span('M • Mantención'),
        ],
    )


def _build_unshift_state() -> Component:
    return html.Div(
        className='gestion-carguio-turno__state gestion-carguio-turno__state--unshift',
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
        class_name='gestion-carguio-turno__status-icon',
    )
    return html.Div(
        className='gestion-carguio-turno__state gestion-carguio-turno__state--unavailable',
        children=[
            *([] if icon is None else [icon]),
            html.Span(message),
        ],
    )
