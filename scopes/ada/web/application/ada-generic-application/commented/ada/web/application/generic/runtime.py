# Espejo comentado: materializa una definición sobre el runtime Atlanticus.
from __future__ import annotations

from ada.configuration.tool_sources import (
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.web.alarms.management_summary import AlarmManagementSummaryState
from ada.web.alarms.status import AlarmStatusState
from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.composition import AdaApplicationComposition
from ada.web.content_state.dependency_resolver import ContentStateDependency
from ada.web.shell.navigation import AdaNavigationView
from ada.web.time_status.store_adapter import TimeStatusStoreSnapshot
from ada.web.ui.content_state import ContentState, ContentStatePresentationMode
from ada.web.ui.global_indicator import GlobalIndicatorCollection
from ada.web.ui.time_status import TimeStatusDetailState
from atlanticus.web.application import create_web_application
from atlanticus.web.models import WebApplicationRuntime


def create_application_runtime(
    *,
    composition: AdaApplicationComposition | None = None,
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
) -> WebApplicationRuntime:
    return create_web_application(
        create_application_definition(
            composition=composition,
            tool_display_name=tool_display_name,
            navigation_view=navigation_view,
            global_indicators=global_indicators,
            global_indicators_content_state=global_indicators_content_state,
            content_state_presentation_mode=content_state_presentation_mode,
            content_state_dependencies=content_state_dependencies,
            alarm_management_summary=alarm_management_summary,
            alarm_status=alarm_status,
            source_consumption=source_consumption,
            source_operational_participation=source_operational_participation,
            time_status_snapshot=time_status_snapshot,
            time_status_detail=time_status_detail,
        )
    )
