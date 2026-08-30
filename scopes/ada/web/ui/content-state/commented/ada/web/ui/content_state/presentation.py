from __future__ import annotations

import re
from collections.abc import Sequence

from dash import html
from dash.development.base_component import Component

from ada.web.ui.core import component_identity_attributes

from .models import ContentState, resolve_content_state, resolve_content_state_visual

# Las claves viajan al DOM como metadata de binding; no definen autoridad de fuente.
_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


# Mantiene el wrapper estable y combina el estado declarativo con el estado runtime inicial.
def build_content_state_wrapper(
    *,
    component_key: str,
    children: Component | Sequence[Component],
    state: ContentState = ContentState.READY,
    runtime_state: ContentState = ContentState.READY,
    tool_key: str | None = None,
    source_keys: Sequence[str] = (),
    class_name: str | None = None,
) -> Component:
    if not isinstance(state, ContentState) or not isinstance(runtime_state, ContentState):
        raise TypeError('Content state wrapper requires ContentState values')

    normalized_source_keys = _normalize_source_keys(source_keys)
    normalized_tool_key = _normalize_tool_key(tool_key, source_keys=normalized_source_keys)
    effective_state = resolve_content_state(state, runtime_state)
    classes = ' '.join(
        part for part in ('ada-content-state', class_name) if isinstance(part, str) and part.strip()
    )
    attributes = component_identity_attributes(component_key)
    attributes['data-ada-content-state'] = effective_state.value
    attributes['data-ada-content-state-declared'] = state.value
    if normalized_source_keys:
        attributes.update(
            {
                'data-ada-content-state-runtime': 'true',
                'data-ada-content-state-tool-key': normalized_tool_key,
                'data-ada-content-state-sources': ','.join(normalized_source_keys),
            }
        )

    return html.Div(
        className=classes,
        children=[
            html.Div(
                className='ada-content-state__content',
                children=children,
            ),
            _build_overlay(state=effective_state),
        ],
        **attributes,
    )


def _build_overlay(*, state: ContentState) -> Component:
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


# La UI valida sólo identidad sintáctica; PI/Dispatch siguen siendo responsabilidad del resolver.
def _normalize_source_keys(source_keys: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(source_keys)
    if len(normalized) != len(set(normalized)):
        raise ValueError('Content State runtime source keys must be unique')
    for source_key in normalized:
        if not isinstance(source_key, str) or not _KEY_PATTERN.fullmatch(source_key):
            raise ValueError(f'Invalid Content State runtime source key: {source_key!r}')
    return normalized


def _normalize_tool_key(tool_key: str | None, *, source_keys: tuple[str, ...]) -> str | None:
    if not source_keys:
        if tool_key is not None:
            raise ValueError('Content State runtime tool_key requires source_keys')
        return None
    if not isinstance(tool_key, str) or not tool_key.strip():
        raise ValueError('Content State runtime source_keys require tool_key')
    return tool_key.strip()
