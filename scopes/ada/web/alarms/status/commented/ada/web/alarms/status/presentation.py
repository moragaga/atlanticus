from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from .models import AlarmStatusState


# Construye únicamente la representación. None significa que la composición todavía no tiene un estado que mostrar.
def build_alarm_status(state: AlarmStatusState | None) -> Component | None:
    if state is None:
        return None
    return html.Div(
        className='ada-alarm-status',
        children=[
            html.Div('Alarmas', className='ada-alarm-status__label'),
            _build_action(kind='active', label='Activas', count=state.active_count),
            _build_action(kind='managed', label='Gestionadas', count=state.managed_count),
        ],
    )


# Se usa un botón desde el inicio porque cada resumen será el punto de entrada a su detalle/modal futuro.
def _build_action(*, kind: str, label: str, count: int) -> Component:
    return html.Button(
        type='button',
        className='ada-alarm-status__action',
        title=f'{label}: {count}',
        **{
            'data-alarm-status-action': kind,
            'aria-label': f'{label}: {count}',
        },
        children=[
            html.Span(str(count), className='ada-alarm-status__count'),
            html.Span(label, className='ada-alarm-status__text'),
        ],
    )
