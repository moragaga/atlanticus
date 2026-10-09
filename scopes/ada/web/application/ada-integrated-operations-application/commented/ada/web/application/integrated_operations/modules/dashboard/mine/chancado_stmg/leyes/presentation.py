from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon

from .models import LeyesMetric, LeyesRow, LeyesState


# La tabla queda al final de Chancado y usa estilos locales para no editar los CSS existentes.
def build_leyes_summary(state: LeyesState) -> Component:
    if not isinstance(state, LeyesState):
        raise TypeError('state must be LeyesState')
    return html.Section(
        [
            html.H3(
                'LEYES',
                style={
                    'margin': 0,
                    'fontSize': '.57rem',
                    'fontWeight': 700,
                    'textAlign': 'center',
                    'background': 'var(--atlanticus-admin-color-border)',
                    'borderRadius': '.2rem',
                },
            ),
            html.Div(
                html.Table(
                    [
                        html.Thead(html.Tr([
                            _header('', '35%', first=True),
                            _header('HORA', '16.25%'),
                            _header('TURNO', '16.25%'),
                            _header('DÍA', '16.25%'),
                            _header('PLAN', '16.25%'),
                        ])),
                        html.Tbody([_row(row) for row in state.rows]),
                    ],
                    style={
                        'borderCollapse': 'collapse',
                        'tableLayout': 'auto',
                        'width': '100%',
                        'minWidth': 'max-content',
                        'fontSize': '.52rem',
                    },
                ),
                style={'width': '100%', 'minWidth': 0, 'overflowX': 'auto'},
            ),
        ],
        style={
            'display': 'flex',
            'flexDirection': 'column',
            'gap': '.18rem',
            'minWidth': 0,
            'width': '100%',
            'padding': '.08rem .18rem',
        },
    )


# Mantiene las cinco columnas contractuales: nombre y cuatro períodos.
def _header(label: str, width: str, *, first: bool = False) -> Component:
    return html.Th(
        label,
        scope='col',
        style={
            'width': width,
            'textAlign': 'left' if first else 'right',
            'padding': '.2rem .15rem',
            'fontWeight': 700,
            'whiteSpace': 'nowrap',
            'borderBottom': '1px solid var(--ada-color-border-primary, #c0c0c0)',
        },
    )


# Solo el nombre admite ellipsis; title conserva la etiqueta completa.
# Cada encabezado de fila lleva una línea inferior, continua con las cuatro celdas de datos.
def _row(row: LeyesRow) -> Component:
    return html.Tr(
        [
            html.Th(
                html.Span(
                    row.label,
                    title=row.label,
                    style={
                        'display': 'block',
                        'maxWidth': '8rem',
                        'minWidth': 0,
                        'overflow': 'hidden',
                        'textOverflow': 'ellipsis',
                        'whiteSpace': 'nowrap',
                    },
                ),
                scope='row',
                style={
                    'textAlign': 'left',
                    'padding': '.2rem .15rem',
                    'fontWeight': 400,
                    'borderBottom': '1px solid var(--ada-color-border-primary, #c0c0c0)',
                },
            ),
            _cell(row.hora),
            _cell(row.turno),
            _cell(row.dia),
            _cell(row.plan),
        ],
        **{'data-leyes-row': row.key},
    )


# Los valores no se recortan: si falta espacio, el contenedor tiene desplazamiento horizontal.
# El borde inferior de cada celda completa la separación entre las filas.
def _cell(metric: LeyesMetric) -> Component:
    return html.Td(
        html.Span(
            _display(metric.value),
            role='button',
            tabIndex=0,
            style={'overflow': 'visible', 'textOverflow': 'clip', 'whiteSpace': 'nowrap'},
            title=metric.kpi_key,
            **{'data-kpi-inspection-key': metric.kpi_key},
        ),
        style={
            'textAlign': 'right',
            'padding': '.2rem .15rem',
            'whiteSpace': 'nowrap',
            'overflow': 'visible',
            'borderBottom': '1px solid var(--ada-color-border-primary, #c0c0c0)',
        },
    )


# Los estados degradados se representan mediante la iconografía común de ADA.
def _display(value: DisplayValue) -> str | Component:
    if value.status is DisplayStatus.OK:
        return str(value.value)
    icon = build_display_status_icon(value.status)
    if icon is None:
        raise ValueError('Leyes status icon cannot be resolved')
    return icon
