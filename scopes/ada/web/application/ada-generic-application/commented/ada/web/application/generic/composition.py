from __future__ import annotations

from dash import html, page_container

from atlanticus.web.services import ServiceRegistry


def build_application_layout(_services: ServiceRegistry):
    # Este es el content slot real. Header, Manager y surfaces se compondrán después alrededor de él.
    return html.Div(
        html.Main(
            page_container,
            id='ada-application-content',
        ),
        id='ada-generic-application',
    )
