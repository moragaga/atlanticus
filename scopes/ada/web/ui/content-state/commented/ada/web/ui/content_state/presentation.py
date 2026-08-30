from __future__ import annotations

from collections.abc import Sequence

from dash import html
from dash.development.base_component import Component

from ada.web.ui.core import component_identity_attributes

from .models import ContentState, resolve_content_state_visual


def build_content_state_wrapper(
    *,
    component_key: str,
    children: Component | Sequence[Component],
    state: ContentState = ContentState.READY,
    class_name: str | None = None,
) -> Component:
    # El wrapper usa component_key como única identidad de dominio del componente.
    if not isinstance(state, ContentState):
        raise TypeError('Content state wrapper requires a ContentState value')

    # La clase del consumidor es opcional y no reemplaza la clase base del contrato.
    classes = ' '.join(
        part for part in ('ada-content-state', class_name) if isinstance(part, str) and part.strip()
    )
    attributes = component_identity_attributes(component_key)
    attributes['data-ada-content-state'] = state.value

    # El contenido real permanece montado debajo del overlay para preservar stores,
    # intervals e interacciones como KPI Inspection.
    return html.Div(
        className=classes,
        children=[
            html.Div(
                className='ada-content-state__content',
                children=children,
            ),
            _build_overlay(state=state),
        ],
        **attributes,
    )


def _build_overlay(*, state: ContentState) -> Component:
    # El overlay siempre existe para permitir cambios de estado sin recrear el contenido.
    return html.Div(
        className='ada-content-state__overlay',
        role='status',
        **{
            'aria-live': 'polite',
            'aria-hidden': 'true' if state is ContentState.READY else 'false',
        },
        children=[
            _build_state_view(ContentState.STALE),
            _build_state_view(ContentState.SOURCE_ERROR),
            _build_state_view(ContentState.CONSTRUCTION),
        ],
    )


def _build_state_view(state: ContentState) -> Component:
    # Cada vista degradada está precargada; CSS muestra solo la asociada al estado actual.
    visual = resolve_content_state_visual(state)
    if visual is None:
        raise RuntimeError('Degraded content state requires a visual definition')

    return html.Div(
        className='ada-content-state__view',
        **{'data-ada-content-state-view': state.value},
        children=[
            html.I(
                className=f'{visual.icon_class} ada-content-state__icon',
                **{'aria-hidden': 'true'},
            ),
            html.P(
                className='ada-content-state__message',
                children=[visual.message],
            ),
        ],
    )
