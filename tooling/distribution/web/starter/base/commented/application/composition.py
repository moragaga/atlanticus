from __future__ import annotations

# La aplicación consumidora conserva la responsabilidad de su propia composición.

import os
from importlib.metadata import version
from pathlib import Path

from dash import html, page_container

from application.modules.example.module import create_example_module
from atlanticus.web.models import ApplicationMetadata, WebApplicationDefinition
from atlanticus.web.services import ServiceRegistry


def create_application_layout(_services: ServiceRegistry):
    return html.Main(page_container, id='application-content')


def create_application_definition() -> WebApplicationDefinition:
    publications_root = Path(
        os.getenv('APPLICATION_PUBLICATIONS_ROOT', '.runtime/publications')
    ).expanduser().resolve()
    return WebApplicationDefinition(
        import_name='application',
        metadata=ApplicationMetadata(
            application_id='application-starter',
            display_name='Application Starter',
            version=version('application-starter'),
        ),
        publications_root=publications_root,
        layout=create_application_layout,
        page_packages=('application.pages',),
        modules=(create_example_module(),),
    )
