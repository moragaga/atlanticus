# Esta capa crea la aplicación Web temporal; no contiene reglas de configuración ni del motor.
# ManagerSurface aporta navegación, workflow y callbacks genéricos del Manager.
from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

from dash import html, page_container

from ada_command_center.web.application.configuration_manager.composition import (
    build_configuration_manager_surface,
)
from ada_command_center.web.application.configuration_manager.dependencies import (
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
_APPLICATION_DISTRIBUTION = 'ada-command-center-configuration-manager'
_PAGE_PACKAGE = 'ada_command_center.web.application.configuration_manager.pages'


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
            className='ada-command-center-configuration-manager',
        )

    return WebApplicationDefinition(
        import_name='ada_command_center.web.application.configuration_manager',
        metadata=ApplicationMetadata(
            application_id='ada-command-center-configuration-manager',
            display_name='ADA Command Center Configuration Manager',
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
