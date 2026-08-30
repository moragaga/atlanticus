from __future__ import annotations

from enum import StrEnum


# Estado operacional compartido; no contiene ninguna responsabilidad de presentación.
class ContentState(StrEnum):
    READY = 'ready'
    STALE = 'stale'
    SOURCE_ERROR = 'source_error'
    CONSTRUCTION = 'construction'


# La precedencia única evita que cada consumidor invente su propia jerarquía de estados.
_STATE_PRIORITY = {
    ContentState.READY: 0,
    ContentState.STALE: 1,
    ContentState.SOURCE_ERROR: 2,
    ContentState.CONSTRUCTION: 3,
}


def resolve_content_state(*states: ContentState) -> ContentState:
    if not states:
        return ContentState.READY
    if any(not isinstance(state, ContentState) for state in states):
        raise TypeError('Content state resolver requires ContentState values')
    return max(states, key=_STATE_PRIORITY.__getitem__)
