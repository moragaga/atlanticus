from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ada.web.content_state.core import ContentState, resolve_content_state


class ContentStatePresentationMode(str, Enum):
    NORMAL = 'normal'
    AUTHORING = 'authoring'


@dataclass(frozen=True, slots=True)
class ContentStateVisual:
    message: str
    icon_class: str


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


def resolve_content_state_visual(state: ContentState) -> ContentStateVisual | None:
    if not isinstance(state, ContentState):
        raise TypeError('Content state visual resolver requires a ContentState value')
    return _STATE_VISUALS.get(state)


__all__ = [
    'ContentState',
    'ContentStatePresentationMode',
    'ContentStateVisual',
    'resolve_content_state',
    'resolve_content_state_visual',
]
