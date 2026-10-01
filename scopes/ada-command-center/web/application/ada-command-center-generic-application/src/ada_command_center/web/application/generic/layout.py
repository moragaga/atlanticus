from __future__ import annotations

from dash import html, page_container

from ada_command_center.web.application.generic.surfaces import (
    MANAGER_SURFACE_ID,
    OPERATIONAL_SURFACE_ID,
)
from atlanticus.web.manager import ManagerSurface
from atlanticus.web.navigation.api import NavigationLink, resolve_navigation_from_services
from atlanticus.web.services import ServiceRegistry


def build_application_layout(
    services: ServiceRegistry,
    *,
    manager: ManagerSurface,
) -> object:
    return html.Div(
        [
            html.Div(
                build_operational_layout(services),
                id=OPERATIONAL_SURFACE_ID,
                hidden=False,
            ),
            html.Div(
                manager.layout(services),
                id=MANAGER_SURFACE_ID,
                hidden=True,
            ),
        ],
        id='ada-command-center-generic-application',
    )


def build_operational_layout(services: ServiceRegistry) -> object:
    menu = resolve_navigation_from_services(services)
    configured = [
        *_links(menu.links),
        *(
            html.Div(
                [html.Strong(group.label), *_links(group.links)],
                className='ada-command-center-navigation-group',
            )
            for group in menu.groups
        ),
    ]
    return html.Div(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.Strong('ADA Command Center'),
                            html.Span(menu.user.display_name),
                        ],
                        className='ada-command-center-header-identity',
                    ),
                    html.Nav(
                        [
                            html.A('Inicio', href='/'),
                            *configured,
                            html.A('Manager', href='/manager'),
                        ],
                        className='ada-command-center-navigation',
                    ),
                ],
                className='ada-command-center-header',
            ),
            html.Main(page_container, id='ada-command-center-content'),
        ],
        id='ada-command-center-operational-application',
    )


def _links(links: tuple[NavigationLink, ...]) -> tuple[object, ...]:
    return tuple(
        html.A(
            link.label,
            href=link.href,
            target='_blank' if link.new_tab else None,
        )
        for link in links
        if link.href not in {'/', '/manager'}
    )
