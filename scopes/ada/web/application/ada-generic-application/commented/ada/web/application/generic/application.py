from __future__ import annotations

from pathlib import Path

from ada.web.application.generic.composition import build_application_layout
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.identity.module import create_identity_module
from atlanticus.web.models import ApplicationMetadata, WebApplicationDefinition
from atlanticus.web.navigation.api import (
    NavigationDefinition,
    NavigationLinkDefinition,
    create_navigation_module,
)

# Mantiene los outputs locales dentro del proyecto de la aplicación, sin depender del cwd.
_APPLICATION_ROOT = Path(__file__).resolve().parents[5]


def create_application_definition() -> WebApplicationDefinition:
    # Navigation ya forma parte del composition root aunque todavía no tenga una UI de menú.
    navigation = NavigationDefinition(
        links=(
            NavigationLinkDefinition(
                key='home',
                label='Inicio',
                href='/',
                order=0,
            ),
        ),
        home_route_key='home',
    )
    return WebApplicationDefinition(
        import_name='ada.web.application.generic',
        metadata=ApplicationMetadata(
            application_id='ada-generic-application',
            display_name='ADA',
            version='0.1.0',
        ),
        publications_root=_APPLICATION_ROOT / '.runtime' / 'publications',
        layout=build_application_layout,
        modules=(
            # El provider local permite levantar la aplicación sin Entra ni infraestructura externa.
            create_identity_module(LocalIdentityProvider()),
            create_navigation_module(navigation),
        ),
        page_packages=('ada.web.application.generic.pages',),
    )
