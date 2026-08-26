from __future__ import annotations

from dash import html, page_container

from ada.web.ui.branding import OperationalBrandState, build_operational_brand
from atlanticus.web.services import ServiceRegistry


def build_application_layout(
    _services: ServiceRegistry,
    *,
    operational_brand: OperationalBrandState,
):
    # El Brand se monta como consumidor real ahora; 05E lo anclará dentro del Header.
    return html.Div(
        [
            build_operational_brand(operational_brand),
            html.Main(
                page_container,
                id='ada-application-content',
            ),
        ],
        id='ada-generic-application',
    )
