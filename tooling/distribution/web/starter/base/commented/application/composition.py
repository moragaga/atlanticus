from __future__ import annotations

import os
from importlib.metadata import version
from pathlib import Path

from atlanticus.web.models import ApplicationMetadata, WebApplicationDefinition
from atlanticus.web.services import ServiceRegistry
from dash import html, page_container


def create_application_layout(_services: ServiceRegistry):
    return html.Main(page_container, id="application-content")


# El Starter base demuestra sólo el contrato mínimo de Atlanticus Web.
def create_application_definition() -> WebApplicationDefinition:
    publications_root = (
        Path(os.getenv("APPLICATION_PUBLICATIONS_ROOT", ".runtime/publications"))
        .expanduser()
        .resolve()
    )
    return WebApplicationDefinition(
        import_name="application",
        metadata=ApplicationMetadata(
            application_id="application-starter",
            display_name="Application Starter",
            version=version("application-starter"),
        ),
        publications_root=publications_root,
        layout=create_application_layout,
        page_packages=("application.pages",),
    )
