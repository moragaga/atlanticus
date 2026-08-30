from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


# Estos estados describen la capacidad operacional del componente completo.
# No reemplazan DisplayStatus, que sigue describiendo valores individuales.
class ContentState(StrEnum):
    READY = 'ready'
    STALE = 'stale'
    SOURCE_ERROR = 'source_error'
    CONSTRUCTION = 'construction'


# El visual se mantiene como dato para que presentación no repita mensajes o iconos.
@dataclass(frozen=True, slots=True)
class ContentStateVisual:
    message: str
    icon_class: str


# La precedencia es explícita y no depende del orden del enum.
_STATE_PRIORITY = {
    ContentState.READY: 0,
    ContentState.STALE: 1,
    ContentState.SOURCE_ERROR: 2,
    ContentState.CONSTRUCTION: 3,
}

# READY no tiene visual porque no debe existir una marca visible en operación normal.
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
    # Sin condiciones degradadas, el componente parte operativo.
    if not states:
        return ContentState.READY
    # Se rechazan strings u otros valores para no crear coerciones implícitas de dominio.
    if any(not isinstance(state, ContentState) for state in states):
        raise TypeError('Content state resolver requires ContentState values')
    # El máximo por prioridad materializa CONSTRUCTION > SOURCE_ERROR > STALE > READY.
    return max(states, key=_STATE_PRIORITY.__getitem__)


def resolve_content_state_visual(state: ContentState) -> ContentStateVisual | None:
    # La UI consume el mismo enum congelado por el contrato.
    if not isinstance(state, ContentState):
        raise TypeError('Content state visual resolver requires a ContentState value')
    return _STATE_VISUALS.get(state)
