from __future__ import annotations

# Se registra un incidente tipado sin registrar detalles potencialmente sensibles.
import logging
from dataclasses import replace
from typing import Protocol

from dash import Input, Output, dcc, html
from dash.development.base_component import Component

from atlanticus.web.models import WebApplicationDefinition
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry

OPERATIONAL_SURFACE_ID = 'ada-operational-surface'
MANAGER_SURFACE_ID = 'ada-manager-surface'
MANAGER_UNAVAILABLE_ID = 'ada-manager-unavailable'
_LOGGER = logging.getLogger(__name__)


# Frontera mínima: no acoplar la composición operacional al Manager concreto.
class ManagerSurfacePort(Protocol):
    @property
    def web_modules(self) -> tuple[WebModule, ...]: ...

    def layout(self, services: ServiceRegistry) -> Component: ...


# Una única definición Flask/Dash aloja ambas superficies conservando rutas propias.
def integrate_manager_surface(
    definition: WebApplicationDefinition,
    *,
    manager: ManagerSurfacePort,
    page_packages: tuple[str, ...],
    route_prefix: str,
    location_id: str,
    unavailable_errors: tuple[type[Exception], ...] = (),
) -> WebApplicationDefinition:
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
    # La degradación sólo acepta excepciones conocidas declaradas por la composición.
    if not isinstance(unavailable_errors, tuple) or any(
        not isinstance(error, type) or not issubclass(error, Exception)
        for error in unavailable_errors
    ):
        raise TypeError('Manager unavailable errors must be exception types')

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

    # Captura la composición operacional previa y la mantiene independiente.
    operational_layout = definition.layout

    # El layout se evalúa por solicitud; un error remoto del Manager no invalida la Web.
    def integrated_layout(services: ServiceRegistry) -> Component:
        operational = operational_layout(services)
        if not isinstance(operational, Component):
            raise TypeError('Integrated operational surface must return a Dash component')
        # Sólo los errores acordados permiten degradar; los defectos de contrato se propagan.
        try:
            administrative = manager.layout(services)
        except unavailable_errors as error:
            _LOGGER.warning(
                'Manager presentation unavailable (%s)',
                type(error).__name__,
            )
            # El fallback conserva la ubicación para que el router siga funcionando.
            administrative = _manager_unavailable_layout(location_id)
        if not isinstance(administrative, Component):
            raise TypeError('Integrated Manager surface must return a Dash component')
        return html.Div(
            [
                html.Div(operational, id=OPERATIONAL_SURFACE_ID, hidden=True),
                html.Div(administrative, id=MANAGER_SURFACE_ID, hidden=True),
            ],
            id='ada-integrated-application',
        )

    return replace(
        definition,
        layout=integrated_layout,
        modules=(*definition.modules, *added_modules),
        page_packages=(*definition.page_packages, *page_packages),
    )


# La persona ve el estado de la superficie administrativa sin exponer secretos.
def _manager_unavailable_layout(location_id: str) -> Component:
    return html.Section(
        [
            dcc.Location(id=location_id, refresh=False),
            html.H2('Manager no disponible'),
            html.P('No fue posible consultar la configuración administrativa.'),
        ],
        id=MANAGER_UNAVAILABLE_ID,
        role='alert',
    )


# El selector por ruta no depende del éxito de la consulta administrativa.
def _create_surface_router(route_prefix: str, location_id: str) -> WebModule:
    def register_callbacks(app: object, _services: ServiceRegistry) -> None:
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
