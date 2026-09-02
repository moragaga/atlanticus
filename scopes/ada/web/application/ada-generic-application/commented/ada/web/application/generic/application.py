# Espejo comentado: composition root ADA; recibe bindings ya resueltos y delega presentación.
from __future__ import annotations

import logging
from dataclasses import replace
from functools import partial
from importlib.metadata import version
from pathlib import Path

from ada.configuration.tool_sources import (
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.web.alarms.management_summary import AlarmManagementSummaryState
from ada.web.alarms.status import AlarmStatusState
from ada.web.application.generic.composition import (
    AdaApplicationComposition,
    create_local_operational_composition,
)
from ada.web.application.generic.operational_render import (
    validate_operational_render_application_binding,
)
from ada.web.content_state.dependency_resolver import ContentStateDependency
from ada.web.operational_render_binding import OperationalRenderBinding
from ada.web.operational_state import resolve_ada_operational_state
from ada.web.shell.navigation import AdaNavigationView
from ada.web.time_status.store_adapter import TimeStatusStoreSnapshot
from ada.web.ui.branding import (
    DEFAULT_OPERATIONAL_BRAND_SECONDARY_LOGO_SRC,
    DEFAULT_PELAMBRES_BRAND_LOGO_SRC,
    OperationalBrandState,
)
from ada.web.ui.content_state import ContentState, ContentStatePresentationMode
from ada.web.ui.global_indicator import GlobalIndicatorCollection
from ada.web.ui.time_status import TimeStatusDetailState
from atlanticus.web.models import ApplicationMetadata, WebApplicationDefinition

_LOGGER = logging.getLogger(__name__)
_APPLICATION_ROOT = Path(__file__).resolve().parents[5]
_APPLICATION_DISTRIBUTION = 'ada-generic-application'


def create_application_definition(
    *,
    composition: AdaApplicationComposition | None = None,
    operational_render_binding: OperationalRenderBinding | None = None,
    tool_display_name: str | None = None,
    navigation_view: AdaNavigationView | None = None,
    global_indicators: GlobalIndicatorCollection | None = None,
    global_indicators_content_state: ContentState = ContentState.READY,
    content_state_presentation_mode: ContentStatePresentationMode = (
        ContentStatePresentationMode.NORMAL
    ),
    content_state_dependencies: tuple[ContentStateDependency, ...] = (),
    alarm_management_summary: AlarmManagementSummaryState | None = None,
    alarm_status: AlarmStatusState | None = None,
    source_consumption: ToolSourceConsumption | None = None,
    source_operational_participation: ToolSourceOperationalParticipation | None = None,
    time_status_snapshot: TimeStatusStoreSnapshot | None = None,
    time_status_detail: TimeStatusDetailState | None = None,
) -> WebApplicationDefinition:
    _validate_content_state_presentation_mode(content_state_presentation_mode)
    if content_state_presentation_mode is ContentStatePresentationMode.AUTHORING:
        _LOGGER.info('Content State presentation override is active: authoring')
    application_version = version(_APPLICATION_DISTRIBUTION)
    operational_brand = OperationalBrandState(context_name=tool_display_name)
    resolved_global_indicators = global_indicators or GlobalIndicatorCollection(())
    operational_state = resolve_ada_operational_state(
        has_global_indicators=bool(len(resolved_global_indicators)),
        content_state_dependencies=content_state_dependencies,
        source_consumption=source_consumption,
        source_operational_participation=source_operational_participation,
        time_status_snapshot=time_status_snapshot,
        time_status_detail=time_status_detail,
    )
    resolved_composition = composition or create_local_operational_composition(
        include_content_state=bool(len(resolved_global_indicators)),
        include_time_status=operational_state.time_status_summary is not None,
    )
    # Un binding sólo es válido si la composición declara cómo renderizarlo.
    validate_operational_render_application_binding(
        binding=operational_render_binding,
        body_factory=resolved_composition.operational_body_factory,
    )
    return WebApplicationDefinition(
        import_name='ada.web.application.generic',
        metadata=ApplicationMetadata(
            application_id='ada-generic-application',
            display_name='ADA',
            version=application_version,
        ),
        publications_root=_APPLICATION_ROOT / '.runtime' / 'publications',
        layout=partial(
            resolved_composition.layout,
            operational_brand=operational_brand,
            navigation_view=_resolve_navigation_view(
                navigation_view,
                application_version=application_version,
            ),
            global_indicators=resolved_global_indicators,
            global_indicators_content_state=global_indicators_content_state,
            content_state_presentation_mode=content_state_presentation_mode,
            global_indicators_runtime_state=(operational_state.global_indicators_runtime_state),
            global_indicators_source_keys=operational_state.global_indicators_source_keys,
            alarm_management_summary=alarm_management_summary,
            alarm_status=alarm_status,
            tool_key=operational_state.tool_key,
            time_status_summary=operational_state.time_status_summary,
            time_status_detail=time_status_detail,
            # El binding cruza intacto hasta el layout; aquí no se inspecciona payload ni ToolKind.
            operational_render_binding=operational_render_binding,
            operational_body_factory=resolved_composition.operational_body_factory,
        ),
        modules=resolved_composition.modules,
        page_packages=resolved_composition.page_packages,
    )


def _validate_content_state_presentation_mode(
    presentation_mode: ContentStatePresentationMode,
) -> None:
    if not isinstance(presentation_mode, ContentStatePresentationMode):
        raise TypeError('Generic Application requires ContentStatePresentationMode value')


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
