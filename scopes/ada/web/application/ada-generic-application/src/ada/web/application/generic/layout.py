from __future__ import annotations

from collections.abc import Callable
from functools import partial

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
from ada.web.ui.content_state import (
    ContentState,
    ContentStatePresentationMode,
    build_content_state_wrapper,
)
from ada.web.ui.global_indicator import GlobalIndicatorCollection, build_global_indicators
from ada.web.ui.time_status import (
    TimeStatusDetailState,
    TimeStatusSummaryState,
    build_time_status,
    build_time_status_detail,
)
from atlanticus.web.navigation.api import resolve_navigation_from_services
from atlanticus.web.services import ServiceRegistry

AdaApplicationLayoutFactory = Callable[..., object]


def create_ada_operational_layout(*, navigation_enabled: bool) -> AdaApplicationLayoutFactory:
    return partial(
        build_operational_application_layout,
        navigation_enabled=navigation_enabled,
    )


def build_operational_application_layout(
    services: ServiceRegistry,
    *,
    operational_brand: OperationalBrandState,
    navigation_view: AdaNavigationView,
    global_indicators: GlobalIndicatorCollection,
    global_indicators_content_state: ContentState,
    content_state_presentation_mode: ContentStatePresentationMode,
    global_indicators_runtime_state: ContentState,
    global_indicators_source_keys: tuple[str, ...],
    alarm_management_summary: AlarmManagementSummaryState | None,
    alarm_status: AlarmStatusState | None,
    tool_key: str | None,
    time_status_summary: TimeStatusSummaryState | None,
    time_status_detail: TimeStatusDetailState | None,
    navigation_enabled: bool,
):
    navigation_offcanvas = None
    desktop_navigation_trigger = None
    mobile_navigation_trigger = None
    if navigation_enabled:
        menu = resolve_navigation_from_services(services)
        desktop_navigation_trigger = build_ada_navigation_desktop_trigger()
        mobile_navigation_trigger = build_ada_navigation_mobile_trigger()
        navigation_offcanvas = build_ada_navigation_offcanvas(menu, view=navigation_view)

    global_indicators_component = _build_global_indicators_component(
        collection=global_indicators,
        content_state=global_indicators_content_state,
        presentation_mode=content_state_presentation_mode,
        runtime_state=global_indicators_runtime_state,
        tool_key=tool_key,
        source_keys=global_indicators_source_keys,
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
        desktop_navigation_trigger=desktop_navigation_trigger,
        mobile_navigation_trigger=mobile_navigation_trigger,
    )
    children = [header]
    if navigation_offcanvas is not None:
        children.append(navigation_offcanvas)
    children.append(
        html.Main(
            page_container,
            id='ada-application-content',
        )
    )
    return html.Div(
        children,
        id='ada-generic-application',
    )


def build_body_application_layout(
    _services: ServiceRegistry,
    **_state: object,
):
    return html.Div(
        html.Main(
            page_container,
            id='ada-application-content',
        ),
        id='ada-generic-application',
    )


def _build_global_indicators_component(
    *,
    collection: GlobalIndicatorCollection,
    content_state: ContentState,
    presentation_mode: ContentStatePresentationMode,
    runtime_state: ContentState,
    tool_key: str | None,
    source_keys: tuple[str, ...],
):
    if not len(collection):
        return None
    return build_content_state_wrapper(
        component_key='global_indicators',
        children=build_global_indicators(collection=collection),
        state=content_state,
        runtime_state=runtime_state,
        presentation_mode=presentation_mode,
        tool_key=tool_key if source_keys else None,
        source_keys=source_keys,
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
