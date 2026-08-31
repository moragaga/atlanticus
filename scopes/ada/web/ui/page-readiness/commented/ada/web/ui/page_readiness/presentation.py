from __future__ import annotations

from dash import html
from dash.development.base_component import Component

# La espera corta comienza sólo después de que todos los callbacks de render declararon readiness.
DEFAULT_PAGE_READINESS_SETTLE_MS = 160
_MIN_SETTLE_MS = 0
_MAX_SETTLE_MS = 2000


def build_page_readiness_scope(
    *,
    content: Component,
    loader: Component,
    enabled: bool = True,
    settle_ms: int = DEFAULT_PAGE_READINESS_SETTLE_MS,
) -> Component:
    # El timeout no decide readiness: sólo deja estabilizar DOM/layout/assets antes del fade.
    if isinstance(settle_ms, bool) or not isinstance(settle_ms, int):
        raise ValueError('Page readiness settle_ms must be an integer')
    if not _MIN_SETTLE_MS <= settle_ms <= _MAX_SETTLE_MS:
        raise ValueError('Page readiness settle_ms must be between 0 and 2000')
    state = 'loading' if enabled else 'ready'
    return html.Div(
        [
            # El contenido queda montado desde el inicio para que Dash y el navegador puedan materializarlo.
            html.Div(content, className='ada-page-readiness__content'),
            # El árbol visual del loader es inyectado por la composición; esta capability no conoce la Tool.
            html.Div(loader, className='ada-page-readiness__loader', hidden=not enabled),
        ],
        className='ada-page-readiness',
        **{
            'aria-busy': 'true' if enabled else 'false',
            'data-ada-page-readiness': 'true',
            'data-ada-page-readiness-enabled': 'true' if enabled else 'false',
            'data-ada-page-readiness-settle-ms': str(settle_ms),
            'data-ada-page-readiness-state': state,
        },
    )
