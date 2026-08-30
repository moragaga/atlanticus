from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ContentState(StrEnum):
    READY = 'ready'
    STALE = 'stale'
    SOURCE_ERROR = 'source_error'
    CONSTRUCTION = 'construction'


@dataclass(frozen=True, slots=True)
class ContentStateVisual:
    message: str
    icon_class: str


_STATE_PRIORITY = {
    ContentState.READY: 0,
    ContentState.STALE: 1,
    ContentState.SOURCE_ERROR: 2,
    ContentState.CONSTRUCTION: 3,
}

_STATE_VISUALS = {
    ContentState.STALE: ContentStateVisual(
        message='Información desactualizada',
        icon_class='bi bi-cloud-slash',
    ),
    ContentState.SOURCE_ERROR: ContentStateVisual(
        message='Fuente de datos con error',
        icon_class='bi bi-exclamation-triangle-fill',
    ),
    ContentState.CONSTRUCTION: ContentStateVisual(
        message='En construcción',
        icon_class='bi bi-hammer',
    ),
}


def resolve_content_state(*states: ContentState) -> ContentState:
    if not states:
        return ContentState.READY
    if any(not isinstance(state, ContentState) for state in states):
        raise TypeError('Content state resolver requires ContentState values')
    return max(states, key=_STATE_PRIORITY.__getitem__)


def resolve_content_state_visual(state: ContentState) -> ContentStateVisual | None:
    if not isinstance(state, ContentState):
        raise TypeError('Content state visual resolver requires a ContentState value')
    return _STATE_VISUALS.get(state)
