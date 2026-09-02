from __future__ import annotations

import re
from dataclasses import dataclass

from ada.web.alarms.management_summary import create_ada_alarm_management_summary_module
from ada.web.alarms.status import create_ada_alarm_status_module
from ada.web.application.generic.layout import (
    AdaApplicationLayoutFactory,
    create_ada_operational_layout,
)
from ada.web.application.generic.operational_render import AdaOperationalBodyFactory
from ada.web.runtime_experience import create_ada_session_module, create_ada_wake_lock_module
from ada.web.shell.header import create_ada_operational_header_module
from ada.web.shell.navigation import create_ada_navigation_presentation_module
from ada.web.ui.branding import create_ada_branding_module
from ada.web.ui.content_state import create_ada_content_state_module
from ada.web.ui.core import create_ada_ui_module
from ada.web.ui.display_status import create_ada_display_status_module
from ada.web.ui.global_indicator import create_ada_global_indicator_module
from ada.web.ui.page_readiness import create_ada_page_readiness_module
from ada.web.ui.time_status import create_ada_time_status_module
from atlanticus.web.identity.access import AccessRuntime
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.identity.module import create_identity_module
from atlanticus.web.modules import WebModule
from atlanticus.web.navigation.api import (
    NavigationDefinition,
    NavigationLinkDefinition,
    NavigationPrincipal,
    NavigationPrincipalProvider,
    NavigationUser,
    create_navigation_module,
)

_DEFAULT_PAGE_PACKAGES = ('ada.web.application.generic.pages',)
_SUBJECT_SEPARATOR = re.compile(r'[-._]+')


@dataclass(frozen=True, slots=True)
class AdaApplicationComposition:
    modules: tuple[WebModule, ...]
    layout: AdaApplicationLayoutFactory
    page_packages: tuple[str, ...] = _DEFAULT_PAGE_PACKAGES
    operational_body_factory: AdaOperationalBodyFactory | None = None


def create_ada_shared_ui_modules(
    *,
    include_content_state: bool = False,
    include_time_status: bool = False,
) -> tuple[WebModule, ...]:
    return (
        create_ada_ui_module(),
        create_ada_display_status_module(),
        create_ada_global_indicator_module(),
        *(() if not include_content_state else (create_ada_content_state_module(),)),
        *(() if not include_time_status else (create_ada_time_status_module(),)),
    )


def create_ada_alarm_surface_modules() -> tuple[WebModule, ...]:
    return (
        create_ada_alarm_management_summary_module(),
        create_ada_alarm_status_module(),
    )


def create_ada_branding_modules() -> tuple[WebModule, ...]:
    return (create_ada_branding_module(),)


def create_local_identity_modules() -> tuple[WebModule, ...]:
    return (create_identity_module(LocalIdentityProvider()),)


def create_identity_navigation_modules() -> tuple[WebModule, ...]:
    return (
        create_navigation_module(
            _default_navigation_definition(),
            principal_provider=NavigationPrincipalProvider(_resolve_bootstrap_navigation_principal),
        ),
    )


def create_ada_operational_shell_modules(*, include_navigation: bool) -> tuple[WebModule, ...]:
    return (
        *(() if not include_navigation else (create_ada_navigation_presentation_module(),)),
        create_ada_operational_header_module(),
    )


def create_ada_runtime_experience_modules() -> tuple[WebModule, ...]:
    return (
        create_ada_session_module(),
        create_ada_wake_lock_module(),
        create_ada_page_readiness_module(),
    )


def create_local_operational_composition(
    *,
    include_content_state: bool = False,
    include_time_status: bool = False,
    operational_body_factory: AdaOperationalBodyFactory | None = None,
) -> AdaApplicationComposition:
    return AdaApplicationComposition(
        modules=(
            *create_ada_shared_ui_modules(
                include_content_state=include_content_state,
                include_time_status=include_time_status,
            ),
            *create_ada_alarm_surface_modules(),
            *create_ada_branding_modules(),
            *create_local_identity_modules(),
            *create_identity_navigation_modules(),
            *create_ada_operational_shell_modules(include_navigation=True),
            *create_ada_runtime_experience_modules(),
        ),
        layout=create_ada_operational_layout(navigation_enabled=True),
        operational_body_factory=operational_body_factory,
    )


def _default_navigation_definition() -> NavigationDefinition:
    return NavigationDefinition(
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
