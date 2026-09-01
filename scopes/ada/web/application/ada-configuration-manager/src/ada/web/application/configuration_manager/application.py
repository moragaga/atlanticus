from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

from dash import html, page_container

from ada.web.application.configuration_manager.composition import (
    build_configuration_manager_surface,
)
from ada.web.application.configuration_manager.dependencies import (
    ConfigurationManagerDependencies,
)
from atlanticus.web.application import create_web_application
from atlanticus.web.manager import ManagerSurface
from atlanticus.web.models import (
    ApplicationMetadata,
    WebApplicationDefinition,
    WebApplicationRuntime,
)

_APPLICATION_ROOT = Path(__file__).resolve().parents[5]
_APPLICATION_DISTRIBUTION = 'ada-configuration-manager'
_PAGE_PACKAGE = 'ada.web.application.configuration_manager.pages'


def create_configuration_manager_web_definition(
    dependencies: ConfigurationManagerDependencies,
) -> WebApplicationDefinition:
    application_version = version(_APPLICATION_DISTRIBUTION)
    surface = ManagerSurface(build_configuration_manager_surface(dependencies))

    def layout(services):
        manager_surface = surface.layout(services)
        return html.Div(
            [
                *manager_surface.children,
                html.Div(page_container, hidden=True),
            ],
            className='ada-configuration-manager',
        )

    return WebApplicationDefinition(
        import_name='ada.web.application.configuration_manager',
        metadata=ApplicationMetadata(
            application_id='ada-configuration-manager',
            display_name='ADA Configuration Manager',
            version=application_version,
        ),
        publications_root=_APPLICATION_ROOT / '.runtime' / 'publications',
        layout=layout,
        modules=surface.web_modules,
        page_packages=(_PAGE_PACKAGE,),
    )


def create_configuration_manager_application(
    dependencies: ConfigurationManagerDependencies,
) -> WebApplicationRuntime:
    return create_web_application(create_configuration_manager_web_definition(dependencies))
