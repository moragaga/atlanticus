# Espejo comentado: la composición selecciona capabilities, layout y factory visual concreto.
from __future__ import annotations

from dataclasses import dataclass

from ada.web.alarms.management_summary import create_ada_alarm_management_summary_module
from ada.web.alarms.status import create_ada_alarm_status_module
from ada.web.application.generic.layout import (
    AdaApplicationLayoutFactory,
    create_ada_operational_layout,
)
from ada.web.application.generic.navigation_binding import public_navigation_principal
from ada.web.application.generic.operational_render import AdaOperationalBodyFactory
from ada.web.branding.web import create_ada_branding_module
from ada.web.runtime_experience import create_ada_session_module, create_ada_wake_lock_module
from ada.web.shell.header import create_ada_operational_header_module
from ada.web.shell.navigation import create_ada_navigation_presentation_module
from ada.web.ui.content_state import create_ada_content_state_module
from ada.web.ui.core import create_ada_ui_module
from ada.web.ui.display_status import create_ada_display_status_module
from ada.web.ui.global_indicator import create_ada_global_indicator_module
from ada.web.ui.page_readiness import create_ada_page_readiness_module
from ada.web.ui.time_status import create_ada_time_status_module
from atlanticus.web.bootstrap import create_bootstrap_foundation_web_module
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.identity.module import create_identity_module
from atlanticus.web.modules import WebModule
from atlanticus.web.navigation.api import (
    NavigationDefinition,
    NavigationDefinitionProvider,
    NavigationPrincipalProvider,
    create_navigation_authorization_module,
    create_navigation_module,
)

_DEFAULT_PAGE_PACKAGES = ('ada.web.application.generic.pages',)


@dataclass(frozen=True, slots=True)
class AdaApplicationComposition:
    modules: tuple[WebModule, ...]
    layout: AdaApplicationLayoutFactory
    page_packages: tuple[str, ...] = _DEFAULT_PAGE_PACKAGES
    # Cada aplicación puede declarar su renderer de body sin imponerlo al runtime genérico.
    operational_body_factory: AdaOperationalBodyFactory | None = None


def create_ada_shared_ui_modules(
    *,
    include_content_state: bool = False,
    include_time_status: bool = False,
) -> tuple[WebModule, ...]:
    return (
        create_bootstrap_foundation_web_module(),
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


def create_operational_navigation_modules(
    *,
    definition_provider: NavigationDefinitionProvider | None = None,
    principal_provider: NavigationPrincipalProvider | None = None,
) -> tuple[WebModule, ...]:
    principal = principal_provider or NavigationPrincipalProvider(public_navigation_principal)
    navigation = (
        create_navigation_module(NavigationDefinition(), principal_provider=principal)
        if definition_provider is None
        else create_navigation_module(
            definition_provider=definition_provider,
            principal_provider=principal,
        )
    )
    return (navigation, create_navigation_authorization_module())


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
    include_identity: bool = False,
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
            *(() if not include_identity else create_local_identity_modules()),
            *create_operational_navigation_modules(),
            *create_ada_operational_shell_modules(include_navigation=True),
            *create_ada_runtime_experience_modules(),
        ),
        layout=create_ada_operational_layout(navigation_enabled=True),
        operational_body_factory=operational_body_factory,
    )



