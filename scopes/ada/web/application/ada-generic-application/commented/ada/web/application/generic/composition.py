from __future__ import annotations

# Composición temporal: Brand y triggers conviven hasta que 05E aporte el Header real.
from dash import html, page_container

from ada.web.shell.navigation import (
    AdaNavigationView,
    build_ada_navigation_desktop_trigger,
    build_ada_navigation_mobile_trigger,
    build_ada_navigation_offcanvas,
)
from ada.web.ui.branding import OperationalBrandState, build_operational_brand
from atlanticus.web.navigation.api import resolve_navigation_from_services
from atlanticus.web.services import ServiceRegistry


def build_application_layout(
    services: ServiceRegistry,
    *,
    operational_brand: OperationalBrandState,
    navigation_view: AdaNavigationView,
):
    menu = resolve_navigation_from_services(services)
    return html.Div(
        [
            html.Div(
                [
                    build_operational_brand(operational_brand),
                    html.Div(
                        build_ada_navigation_mobile_trigger(),
                        className='ada-navigation__mobile-anchor',
                    ),
                    build_ada_navigation_desktop_trigger(),
                ],
                className='ada-navigation__anchor-host d-flex align-items-center justify-content-between gap-3 p-3',
            ),
            build_ada_navigation_offcanvas(menu, view=navigation_view),
            html.Main(
                page_container,
                id='ada-application-content',
            ),
        ],
        id='ada-generic-application',
    )
