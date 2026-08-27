from __future__ import annotations

from dash import html, page_container

from ada.web.shell.header import build_ada_operational_header
from ada.web.shell.navigation import (
    AdaNavigationView,
    build_ada_navigation_desktop_trigger,
    build_ada_navigation_mobile_trigger,
    build_ada_navigation_offcanvas,
)
from ada.web.ui.branding import OperationalBrandState, build_operational_brand
from ada.web.ui.global_indicator import GlobalIndicatorCollection, build_global_indicators
from atlanticus.web.navigation.api import resolve_navigation_from_services
from atlanticus.web.services import ServiceRegistry


def build_application_layout(
    services: ServiceRegistry,
    *,
    operational_brand: OperationalBrandState,
    navigation_view: AdaNavigationView,
    global_indicators: GlobalIndicatorCollection,
):
    menu = resolve_navigation_from_services(services)
    global_indicators_component = (
        build_global_indicators(collection=global_indicators) if len(global_indicators) else None
    )
    header = build_ada_operational_header(
        brand=build_operational_brand(operational_brand),
        global_indicators=global_indicators_component,
        desktop_navigation_trigger=build_ada_navigation_desktop_trigger(),
        mobile_navigation_trigger=build_ada_navigation_mobile_trigger(),
    )
    return html.Div(
        [
            header,
            build_ada_navigation_offcanvas(menu, view=navigation_view),
            html.Main(
                page_container,
                id='ada-application-content',
            ),
        ],
        id='ada-generic-application',
    )
