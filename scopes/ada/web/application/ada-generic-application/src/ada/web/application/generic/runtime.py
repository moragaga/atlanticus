from __future__ import annotations

from ada.web.alarms.management_summary import AlarmManagementSummaryState
from ada.web.application.generic.application import create_application_definition
from ada.web.shell.navigation import AdaNavigationView
from ada.web.ui.global_indicator import GlobalIndicatorCollection
from atlanticus.web.application import create_web_application
from atlanticus.web.models import WebApplicationRuntime


def create_application_runtime(
    *,
    tool_display_name: str | None = None,
    navigation_view: AdaNavigationView | None = None,
    global_indicators: GlobalIndicatorCollection | None = None,
    alarm_management_summary: AlarmManagementSummaryState | None = None,
) -> WebApplicationRuntime:
    return create_web_application(
        create_application_definition(
            tool_display_name=tool_display_name,
            navigation_view=navigation_view,
            global_indicators=global_indicators,
            alarm_management_summary=alarm_management_summary,
        )
    )
