from __future__ import annotations

from dash import html, page_container

from atlanticus.web.services import ServiceRegistry


def build_application_layout(_services: ServiceRegistry):
    return html.Div(
        html.Main(
            page_container,
            id='ada-application-content',
        ),
        id='ada-generic-application',
    )
