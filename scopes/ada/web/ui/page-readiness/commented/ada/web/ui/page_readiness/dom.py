from __future__ import annotations

# Los callbacks escriben estas propiedades sobre su wrapper estable; no se crea un Store paralelo.
COMPONENT_KEY_PROPERTY = 'data-ada-component-key'
RENDER_READY_PROPERTY = 'data-ada-render-ready'
PAGE_READINESS_STATE_PROPERTY = 'data-ada-page-readiness-state'


def build_render_ready_attributes(component_key: str, *, ready: bool = False) -> dict[str, str]:
    # La identidad reutiliza la key estable del componente y evita una segunda jerarquía de IDs.
    normalized = component_key.strip() if isinstance(component_key, str) else ''
    if not normalized:
        raise ValueError('Page readiness component key must be a non-empty string')
    return {
        COMPONENT_KEY_PROPERTY: normalized,
        RENDER_READY_PROPERTY: 'true' if ready else 'false',
    }
