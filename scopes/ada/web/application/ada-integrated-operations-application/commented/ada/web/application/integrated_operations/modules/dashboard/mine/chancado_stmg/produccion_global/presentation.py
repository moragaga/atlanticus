# Compone AVANCE, CIERRE y RITMO; cada valor tiene su propia clave inspeccionable y foco por teclado.
from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon

from .models import ProduccionGlobalMetric, ProduccionGlobalRow, ProduccionGlobalState


def build_produccion_global(state: ProduccionGlobalState) -> Component:
    if not isinstance(state, ProduccionGlobalState):
        raise TypeError('state must be ProduccionGlobalState')
    return html.Section(
        className='ada-io-produccion-global',
        children=[
            html.H3('PRODUCCIÓN GLOBAL', className='ada-io-produccion-global__title'),
            html.Div(
                className='ada-io-produccion-global__header',
                children=[
                    _header_column('AVANCE', 'Real / Plan acum.'),
                    _header_column('CIERRE', 'Proy. / Plan día'),
                    _header_column('RITMO', 'Req./h'),
                ],
            ),
            html.Div(
                [_row(row) for row in state.rows],
                className='ada-io-produccion-global__rows',
            ),
        ],
    )


def _header_column(title: str, subtitle: str) -> Component:
    return html.Div(
        className='ada-io-produccion-global__header-column',
        children=[
            html.Span(title, className='ada-io-produccion-global__header-title'),
            html.Span(subtitle, className='ada-io-produccion-global__header-subtitle'),
        ],
    )


def _row(row: ProduccionGlobalRow) -> Component:
    return html.Div(
        className='ada-io-produccion-global__row',
        **{'data-produccion-global-row': row.key},
        children=[
            html.Div(f'{row.label} (kt)', className='ada-io-produccion-global__row-label'),
            html.Div(
                className='ada-io-produccion-global__metrics',
                children=[
                    _comparison(row.real, row.plan_acumulado),
                    _comparison(row.proyeccion, row.plan_dia),
                    html.Div(
                        className='ada-io-produccion-global__metric',
                        children=[
                            _value(row.requerido_hora, prominent=True),
                            html.Span('/h', className='ada-io-produccion-global__unit'),
                        ],
                    ),
                ],
            ),
        ],
    )


def _comparison(first: ProduccionGlobalMetric, second: ProduccionGlobalMetric) -> Component:
    return html.Div(
        className='ada-io-produccion-global__metric',
        children=[
            _value(first, prominent=True),
            html.Span('/', className='ada-io-produccion-global__separator'),
            _value(second, prominent=False),
        ],
    )


# Incluso las lecturas degradadas mantienen una clave inspeccionable.
def _value(metric: ProduccionGlobalMetric, *, prominent: bool) -> Component:
    class_name = 'ada-io-produccion-global__value'
    if prominent:
        class_name += ' ada-io-produccion-global__value--prominent'
    return html.Span(
        _display(metric.value),
        className=class_name,
        role='button',
        tabIndex=0,
        title=metric.kpi_key,
        **{'data-kpi-inspection-key': metric.kpi_key},
    )


def _display(value: DisplayValue) -> str | Component:
    if value.status is DisplayStatus.OK:
        return str(value.value)
    icon = build_display_status_icon(
        value.status,
        class_name='ada-io-produccion-global__status-icon',
    )
    if icon is None:
        raise ValueError('Produccion Global status icon cannot be resolved')
    return icon
