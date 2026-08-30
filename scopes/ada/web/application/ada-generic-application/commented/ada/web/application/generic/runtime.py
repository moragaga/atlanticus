# Factory de runtime con estados de presentación ya resueltos e inyectados desde composición externa.
from __future__ import annotations

from ada.web.alarms.management_summary import AlarmManagementSummaryState
from ada.web.alarms.status import AlarmStatusState
from ada.web.application.generic.application import create_application_definition
from ada.web.shell.navigation import AdaNavigationView
from ada.web.ui.content_state import ContentState
from ada.web.ui.global_indicator import GlobalIndicatorCollection
from ada.web.ui.time_status import TimeStatusDetailState, TimeStatusSummaryState
from atlanticus.web.application import create_web_application
from atlanticus.web.models import WebApplicationRuntime


def create_application_runtime(
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
) -> WebApplicationRuntime:
    # El runtime no resuelve freshness: sólo propaga el ContentState recibido a la composición.
    return create_web_application(
        create_application_definition(
            tool_display_name=tool_display_name,
            navigation_view=navigation_view,
            global_indicators=global_indicators,
            global_indicators_content_state=global_indicators_content_state,
            alarm_management_summary=alarm_management_summary,
            alarm_status=alarm_status,
            tool_key=tool_key,
            time_status_summary=time_status_summary,
            time_status_detail=time_status_detail,
        )
    )
