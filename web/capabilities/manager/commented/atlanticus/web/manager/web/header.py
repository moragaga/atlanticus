from __future__ import annotations

from dash import dcc, html

from atlanticus.web.manager.authorization import ManagerAuthorizationPolicy
from atlanticus.web.manager.models import ManagerPrincipal
from atlanticus.web.manager.registry import ManagerModuleRegistry
from atlanticus.web.manager.web.ids import HEADER_SECTION_ID


# Header genérico y permanente. No reutiliza el header operacional de ADA.
def build_manager_header(
    *,
    registry: ManagerModuleRegistry,
    principal: ManagerPrincipal,
    application_home_href: str | None,
) -> object:
    # Manager Home siempre existe; el anfitrión aporta opcionalmente su ruta de retorno.
    actions = [
        dcc.Link(
            'Manager Home',
            href=registry.root_route,
            className='atlanticus-manager__header-link',
        )
    ]
    if application_home_href is not None:
        actions.append(
            dcc.Link(
                'Volver a la aplicación',
                href=application_home_href,
                className='atlanticus-manager__header-link atlanticus-manager__header-link--return',
            )
        )
    return html.Header(
        [
            html.Div(
                [
                    html.Strong('ATLANTICUS', className='atlanticus-manager__header-brand'),
                    html.Div(
                        [
                            html.Span('Manager', className='atlanticus-manager__header-name'),
                            html.Span('Inicio', id=HEADER_SECTION_ID,
                                      className='atlanticus-manager__header-section'),
                        ],
                        className='atlanticus-manager__header-context',
                    ),
                ],
                className='atlanticus-manager__header-identity',
            ),
            html.Div(
                [
                    html.Nav(
                        actions,
                        className='atlanticus-manager__header-actions',
                        **{'aria-label': 'Accesos del Manager'},
                    ),
                    html.Span(
                        principal.display_name,
                        className='atlanticus-manager__header-principal',
                        **{'aria-label': 'Usuario actual'},
                    ),
                ],
                className='atlanticus-manager__header-end',
            ),
        ],
        className='atlanticus-manager__header',
    )


# Una ruta no autorizada jamás revela el título de la capacidad restringida.
def resolve_manager_header_section(
    *,
    pathname: str | None,
    registry: ManagerModuleRegistry,
    principal: ManagerPrincipal,
    authorization: ManagerAuthorizationPolicy,
) -> str:
    route = pathname or registry.root_route
    if route == registry.root_route:
        return 'Inicio'
    item = registry.find_by_route(route)
    if item is None or not authorization.can_view(principal, item):
        return 'Administración'
    return item.title
