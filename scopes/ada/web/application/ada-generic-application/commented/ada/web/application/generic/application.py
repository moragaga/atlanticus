# La composition root conecta Identity con Navigation Core sólo para el bootstrap local, sin mover esa responsabilidad al componente visual.
from __future__ import annotations

import re
from functools import partial
from pathlib import Path

from ada.web.application.generic.composition import build_application_layout
from ada.web.shell.navigation import AdaNavigationView, create_ada_navigation_presentation_module
from ada.web.ui.branding import OperationalBrandState, create_ada_branding_module
from ada.web.ui.core import create_ada_ui_module
from atlanticus.web.identity.access import AccessRuntime
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.identity.module import create_identity_module
from atlanticus.web.models import ApplicationMetadata, WebApplicationDefinition
from atlanticus.web.navigation.api import (
    NavigationDefinition,
    NavigationLinkDefinition,
    NavigationPrincipal,
    NavigationPrincipalProvider,
    NavigationUser,
    create_navigation_module,
)

_APPLICATION_ROOT = Path(__file__).resolve().parents[5]
_SUBJECT_SEPARATOR = re.compile(r'[-._]+')


def create_application_definition(
    *,
    tool_display_name: str | None = None,
    navigation_view: AdaNavigationView | None = None,
) -> WebApplicationDefinition:
    navigation = NavigationDefinition(
        links=(
            NavigationLinkDefinition(
                key='home',
                label='Inicio',
                href='/',
                order=0,
                icon='bi bi-house',
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
            version='0.1.3',
        ),
        publications_root=_APPLICATION_ROOT / '.runtime' / 'publications',
        layout=partial(
            build_application_layout,
            operational_brand=operational_brand,
            navigation_view=navigation_view or AdaNavigationView(),
        ),
        modules=(
            create_ada_ui_module(),
            create_ada_branding_module(),
            create_identity_module(LocalIdentityProvider()),
            create_navigation_module(
                navigation,
                principal_provider=NavigationPrincipalProvider(
                    _resolve_bootstrap_navigation_principal
                ),
            ),
            create_ada_navigation_presentation_module(),
        ),
        page_packages=('ada.web.application.generic.pages',),
    )


def _resolve_bootstrap_navigation_principal() -> NavigationPrincipal:
    snapshot = AccessRuntime().current()
    identity = snapshot.identity
    if identity is None:
        raise RuntimeError('Resolved access snapshot does not contain an identity')
    display_name = identity.display_name or _display_name_from_subject(identity.subject_id)
    profile_key = identity.provider_key
    return NavigationPrincipal(
        access_key=profile_key,
        unrestricted=True,
        user=NavigationUser(
            display_name=display_name,
            email=identity.email,
            profile_key=profile_key,
            profile_label=profile_key.replace('-', ' ').title(),
            profile_background_color='#3778C2',
            profile_text_color='#FFFFFF',
            avatar_text=_avatar_text(display_name),
        ),
    )


def _display_name_from_subject(subject_id: str) -> str:
    candidate = subject_id.rsplit(':', maxsplit=1)[-1].strip()
    words = _SUBJECT_SEPARATOR.sub(' ', candidate).split()
    if not words:
        return subject_id
    return ' '.join(word.capitalize() for word in words)


def _avatar_text(display_name: str) -> str:
    words = display_name.split()
    if not words:
        return 'U'
    return ''.join(word[0] for word in words[:2]).upper()
