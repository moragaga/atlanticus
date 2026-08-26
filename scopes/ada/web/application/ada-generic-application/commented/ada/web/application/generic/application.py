# Composition root real de ADA. Desde este step la aplicación registra explícitamente la fundación
# visual ADA antes de las capabilities funcionales, sin incorporar aún Header ni Branding.
from __future__ import annotations

from pathlib import Path

from ada.web.application.generic.composition import build_application_layout
from ada.web.ui.core import create_ada_ui_module
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.identity.module import create_identity_module
from atlanticus.web.models import ApplicationMetadata, WebApplicationDefinition
from atlanticus.web.navigation.api import (
    NavigationDefinition,
    NavigationLinkDefinition,
    create_navigation_module,
)

_APPLICATION_ROOT = Path(__file__).resolve().parents[5]


def create_application_definition() -> WebApplicationDefinition:
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
            version='0.1.1',
        ),
        publications_root=_APPLICATION_ROOT / '.runtime' / 'publications',
        layout=build_application_layout,
        modules=(
            create_ada_ui_module(),
            create_identity_module(LocalIdentityProvider()),
            create_navigation_module(navigation),
        ),
        page_packages=('ada.web.application.generic.pages',),
    )
