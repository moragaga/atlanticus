from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from dash import Input, Output, html
from dash.development.base_component import Component

from atlanticus.web.models import WebApplicationDefinition
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry

# Cada superficie es responsable de sus módulos, callbacks y layout.
# La composición de ADA controla únicamente su montaje y selección por ruta.
OPERATIONAL_SURFACE_ID = 'ada-operational-surface'
MANAGER_SURFACE_ID = 'ada-manager-surface'


# Este contrato evita que el núcleo de ADA dependa de una aplicación Manager independiente.
# La implementación real es la capability Manager existente.
class ManagerSurfacePort(Protocol):
    @property
    def web_modules(self) -> tuple[WebModule, ...]: ...

    def layout(self, services: ServiceRegistry) -> Component: ...


def integrate_manager_surface(
    definition: WebApplicationDefinition,
    *,
    manager: ManagerSurfacePort,
    page_packages: tuple[str, ...],
    route_prefix: str,
    location_id: str,
) -> WebApplicationDefinition:
    # Validar antes del montaje para no entregar una definición ambigua a Dash.
    if not isinstance(definition, WebApplicationDefinition):
        raise TypeError('definition must be a WebApplicationDefinition')
    if not isinstance(route_prefix, str) or not route_prefix.startswith('/') or route_prefix == '/':
        raise ValueError('route_prefix must be a non-root absolute route')
    if route_prefix.endswith('/'):
        raise ValueError('route_prefix must not end in a slash')
    if not isinstance(location_id, str) or not location_id.strip():
        raise ValueError('Manager location_id must not be empty')
    if not page_packages or any(
        not isinstance(name, str) or not name.strip() for name in page_packages
    ):
        raise ValueError('Manager page packages must not be empty')

    router = _create_surface_router(route_prefix, location_id)
    added_modules = (*manager.web_modules, router)
    existing_names = {module.name for module in definition.modules}
    added_names = [module.name for module in added_modules]
    if existing_names.intersection(added_names) or len(added_names) != len(set(added_names)):
        raise ValueError('Integrated Web modules must have unique names')
    if len(page_packages) != len(set(page_packages)) or set(definition.page_packages).intersection(
        page_packages
    ):
        raise ValueError('Manager page packages are already registered')

    operational_layout = definition.layout

    def integrated_layout(services: ServiceRegistry) -> Component:
        # Mantener los dos shells en un solo árbol Dash: ninguno absorbe al otro.
        # Los componentes permanecen montados para que sus callbacks tengan destinos.
        operational = operational_layout(services)
        administrative = manager.layout(services)
        if not isinstance(operational, Component) or not isinstance(administrative, Component):
            raise TypeError('Integrated surfaces must return Dash components')
        return html.Div(
            [
                html.Div(operational, id=OPERATIONAL_SURFACE_ID, hidden=True),
                html.Div(administrative, id=MANAGER_SURFACE_ID, hidden=True),
            ],
            id='ada-integrated-application',
        )

    # No crear un segundo Flask/Dash: componer los módulos sobre la definición recibida.
    return replace(
        definition,
        layout=integrated_layout,
        modules=(*definition.modules, *added_modules),
        page_packages=(*definition.page_packages, *page_packages),
    )


def _create_surface_router(route_prefix: str, location_id: str) -> WebModule:
    def register_callbacks(app: object, _services: ServiceRegistry) -> None:
        # Distinguir /manager de rutas que simplemente comienzan con ese texto.
        @app.callback(
            Output(OPERATIONAL_SURFACE_ID, 'hidden'),
            Output(MANAGER_SURFACE_ID, 'hidden'),
            Input(location_id, 'pathname'),
        )
        def select_surface(pathname: str | None) -> tuple[bool, bool]:
            manager_route = pathname == route_prefix or bool(
                pathname and pathname.startswith(f'{route_prefix}/')
            )
            return manager_route, not manager_route

    return WebModule(name='ada-manager-surface-router', register_callbacks=register_callbacks)
