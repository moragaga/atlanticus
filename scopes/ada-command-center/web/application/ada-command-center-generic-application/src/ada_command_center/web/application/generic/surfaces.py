from __future__ import annotations

from dash import Input, Output

from atlanticus.web.manager.web.ids import LOCATION_ID
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry

OPERATIONAL_SURFACE_ID = 'ada-command-center-operational-surface'
MANAGER_SURFACE_ID = 'ada-command-center-manager-surface'


def surface_visibility(
    pathname: str | None,
    *,
    route_prefix: str,
) -> tuple[bool, bool]:
    if not isinstance(route_prefix, str) or not route_prefix.startswith('/') or route_prefix == '/':
        raise ValueError('route_prefix must be a non-root absolute route')
    if route_prefix.endswith('/'):
        raise ValueError('route_prefix must not end in a slash')
    manager_route = pathname == route_prefix or bool(
        pathname and pathname.startswith(f'{route_prefix}/')
    )
    return manager_route, not manager_route


def create_surface_router_module(*, route_prefix: str) -> WebModule:
    surface_visibility(None, route_prefix=route_prefix)

    def register_callbacks(app: object, _services: ServiceRegistry) -> None:
        @app.callback(
            Output(OPERATIONAL_SURFACE_ID, 'hidden'),
            Output(MANAGER_SURFACE_ID, 'hidden'),
            Input(LOCATION_ID, 'pathname'),
        )
        def select_surface(pathname: str | None) -> tuple[bool, bool]:
            return surface_visibility(pathname, route_prefix=route_prefix)

    return WebModule(
        name='ada-command-center-surface-router',
        register_callbacks=register_callbacks,
    )
