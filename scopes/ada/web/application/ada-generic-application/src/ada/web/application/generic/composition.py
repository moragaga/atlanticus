from __future__ import annotations

from dash import html, page_container

from ada.web.alarms.management_summary import (
    AlarmManagementSummaryState,
    build_alarm_management_summary,
)
from ada.web.alarms.status import AlarmStatusState, build_alarm_status
from ada.web.shell.header import build_ada_operational_header
from ada.web.shell.navigation import (
    AdaNavigationView,
    build_ada_navigation_desktop_trigger,
    build_ada_navigation_mobile_trigger,
    build_ada_navigation_offcanvas,
)
from ada.web.ui.branding import OperationalBrandState, build_operational_brand
from ada.web.ui.content_state import ContentState, build_content_state_wrapper
from ada.web.ui.global_indicator import GlobalIndicatorCollection, build_global_indicators
from ada.web.ui.time_status import (
    TimeStatusDetailState,
    TimeStatusSummaryState,
    build_time_status,
    build_time_status_detail,
)
from atlanticus.web.navigation.api import resolve_navigation_from_services
from atlanticus.web.services import ServiceRegistry


def build_application_layout(
    services: ServiceRegistry,
    *,
    operational_brand: OperationalBrandState,
    navigation_view: AdaNavigationView,
    global_indicators: GlobalIndicatorCollection,
    global_indicators_content_state: ContentState,
    alarm_management_summary: AlarmManagementSummaryState | None,
    alarm_status: AlarmStatusState | None,
    tool_key: str | None,
    time_status_summary: TimeStatusSummaryState | None,
    time_status_detail: TimeStatusDetailState | None,
):
    menu = resolve_navigation_from_services(services)
    global_indicators_component = _build_global_indicators_component(
        collection=global_indicators,
        content_state=global_indicators_content_state,
    )
    alarm_management_component = build_alarm_management_summary(alarm_management_summary)
    alarm_status_component = build_alarm_status(alarm_status)
    time_status_component = _build_time_status_component(
        tool_key=tool_key,
        summary=time_status_summary,
        detail=time_status_detail,
    )
    header = build_ada_operational_header(
        brand=build_operational_brand(operational_brand),
        global_indicators=global_indicators_component,
        alarm_management=alarm_management_component,
        alarm_status=alarm_status_component,
        time_status=time_status_component,
        desktop_navigation_trigger=build_ada_navigation_desktop_trigger(),
        mobile_navigation_trigger=build_ada_navigation_mobile_trigger(),
    )
    return html.Div(
        [
            header,
            build_ada_navigation_offcanvas(menu, view=navigation_view),
            html.Main(
                page_container,
                id='ada-application-content',
            ),
        ],
        id='ada-generic-application',
    )


def _build_global_indicators_component(
    *,
    collection: GlobalIndicatorCollection,
    content_state: ContentState,
):
    if not len(collection):
        return None
    return build_content_state_wrapper(
        component_key='global_indicators',
        children=build_global_indicators(collection=collection),
        state=content_state,
    )


def _build_time_status_component(
    *,
    tool_key: str | None,
    summary: TimeStatusSummaryState | None,
    detail: TimeStatusDetailState | None,
):
    if summary is None:
        if detail is not None:
            raise ValueError('Time Status detail requires Time Status summary')
        return None
    return build_time_status(
        tool_key=tool_key or '',
        state=summary,
        detail=None if detail is None else build_time_status_detail(state=detail),
    )
