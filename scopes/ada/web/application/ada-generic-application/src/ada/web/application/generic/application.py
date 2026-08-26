from __future__ import annotations

from functools import partial
from pathlib import Path

from ada.web.application.generic.composition import build_application_layout
from ada.web.ui.branding import OperationalBrandState, create_ada_branding_module
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


def create_application_definition(
    *,
    tool_display_name: str | None = None,
) -> WebApplicationDefinition:
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
    operational_brand = OperationalBrandState(context_name=tool_display_name)
    return WebApplicationDefinition(
        import_name='ada.web.application.generic',
        metadata=ApplicationMetadata(
            application_id='ada-generic-application',
            display_name='ADA',
            version='0.1.2',
        ),
        publications_root=_APPLICATION_ROOT / '.runtime' / 'publications',
        layout=partial(build_application_layout, operational_brand=operational_brand),
        modules=(
            create_ada_ui_module(),
            create_ada_branding_module(),
            create_identity_module(LocalIdentityProvider()),
            create_navigation_module(navigation),
        ),
        page_packages=('ada.web.application.generic.pages',),
    )
