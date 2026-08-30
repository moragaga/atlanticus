# Composition root: registra Content State sólo cuando existe un consumidor real.
from __future__ import annotations

import re
from dataclasses import replace
from functools import partial
from importlib.metadata import version
from pathlib import Path

from ada.web.alarms.management_summary import (
    AlarmManagementSummaryState,
    create_ada_alarm_management_summary_module,
)
from ada.web.alarms.status import (
    AlarmStatusState,
    create_ada_alarm_status_module,
)
from ada.web.application.generic.composition import build_application_layout
from ada.web.shell.header import create_ada_operational_header_module
from ada.web.shell.navigation import AdaNavigationView, create_ada_navigation_presentation_module
from ada.web.ui.branding import (
    DEFAULT_OPERATIONAL_BRAND_SECONDARY_LOGO_SRC,
    DEFAULT_PELAMBRES_BRAND_LOGO_SRC,
    OperationalBrandState,
    create_ada_branding_module,
)
from ada.web.ui.content_state import ContentState, create_ada_content_state_module
from ada.web.ui.core import create_ada_ui_module
from ada.web.ui.display_status import create_ada_display_status_module
from ada.web.ui.global_indicator import (
    GlobalIndicatorCollection,
    create_ada_global_indicator_module,
)
from ada.web.ui.time_status import (
    TimeStatusDetailState,
    TimeStatusSummaryState,
    create_ada_time_status_module,
)
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
_APPLICATION_DISTRIBUTION = 'ada-generic-application'
_SUBJECT_SEPARATOR = re.compile(r'[-._]+')


def create_application_definition(
    *,
    tool_display_name: str | None = None,
    navigation_view: AdaNavigationView | None = None,
    global_indicators: GlobalIndicatorCollection | None = None,
    global_indicators_content_state: ContentState = ContentState.READY,
    alarm_management_summary: AlarmManagementSummaryState | None = None,
    alarm_status: AlarmStatusState | None = None,
    tool_key: str | None = None,
    time_status_summary: TimeStatusSummaryState | None = None,
    time_status_detail: TimeStatusDetailState | None = None,
) -> WebApplicationDefinition:
    application_version = version(_APPLICATION_DISTRIBUTION)
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
    # La colección resuelta determina tanto el layout como si corresponde cargar el asset de Content State.
    resolved_global_indicators = global_indicators or GlobalIndicatorCollection(())
    return WebApplicationDefinition(
        import_name='ada.web.application.generic',
        metadata=ApplicationMetadata(
            application_id='ada-generic-application',
            display_name='ADA',
            version=application_version,
        ),
        publications_root=_APPLICATION_ROOT / '.runtime' / 'publications',
        layout=partial(
            build_application_layout,
            operational_brand=operational_brand,
            navigation_view=_resolve_navigation_view(
                navigation_view,
                application_version=application_version,
            ),
            global_indicators=resolved_global_indicators,
            global_indicators_content_state=global_indicators_content_state,
            alarm_management_summary=alarm_management_summary,
            alarm_status=alarm_status,
            tool_key=tool_key,
            time_status_summary=time_status_summary,
            time_status_detail=time_status_detail,
        ),
        modules=(
            create_ada_ui_module(),
            create_ada_display_status_module(),
            create_ada_global_indicator_module(),
            # Content State se carga sólo cuando Global Indicators realmente existe.
            *(() if not len(resolved_global_indicators) else (create_ada_content_state_module(),)),
            *(() if time_status_summary is None else (create_ada_time_status_module(),)),
            create_ada_alarm_management_summary_module(),
            create_ada_alarm_status_module(),
            create_ada_branding_module(),
            create_identity_module(LocalIdentityProvider()),
            create_navigation_module(
                navigation,
                principal_provider=NavigationPrincipalProvider(
                    _resolve_bootstrap_navigation_principal
                ),
            ),
            create_ada_navigation_presentation_module(),
            create_ada_operational_header_module(),
        ),
        page_packages=('ada.web.application.generic.pages',),
    )


def _resolve_navigation_view(
    view: AdaNavigationView | None,
    *,
    application_version: str,
) -> AdaNavigationView:
    resolved = view or AdaNavigationView()
    return replace(
        resolved,
        brand_logo_src=(resolved.brand_logo_src or DEFAULT_OPERATIONAL_BRAND_SECONDARY_LOGO_SRC),
        footer_logo_src=resolved.footer_logo_src or DEFAULT_PELAMBRES_BRAND_LOGO_SRC,
        application_version=resolved.application_version or application_version,
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
