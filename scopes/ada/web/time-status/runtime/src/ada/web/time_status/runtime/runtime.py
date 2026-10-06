from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING

from dash import Input, Output, html
from dash.development.base_component import Component

from ada.web.kpis.collector import system_kpi_store_id
from ada.web.ui.time_status import build_time_status, build_time_status_detail
from atlanticus.web.modules import WebModule

from .binding import TimeStatusRuntimeBinding
from .resolver import resolve_time_status_summary

if TYPE_CHECKING:
    from dash import Dash

TIME_STATUS_RUNTIME_HOST_TYPE = 'ada-time-status-runtime-host'
TIME_STATUS_DESTINATION_KEY = 'time_status'
_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


def time_status_runtime_host_id(tool_key: str) -> dict[str, str]:
    if not isinstance(tool_key, str) or _KEY_PATTERN.fullmatch(tool_key) is None:
        raise ValueError('Time Status runtime tool_key has an invalid format')
    return {'type': TIME_STATUS_RUNTIME_HOST_TYPE, 'tool': tool_key}


def build_time_status_runtime_host(binding: TimeStatusRuntimeBinding) -> Component:
    _require_binding(binding)
    return html.Div(
        build_time_status_runtime_component(None, binding=binding),
        id=time_status_runtime_host_id(binding.tool_key),
        **{'data-ada-time-status-runtime-host': 'true'},
    )


def build_time_status_runtime_component(
    store_data: object,
    *,
    binding: TimeStatusRuntimeBinding,
    now_utc: datetime | None = None,
) -> Component:
    _require_binding(binding)
    summary = resolve_time_status_summary(store_data, binding=binding, now_utc=now_utc)
    detail = None if binding.detail is None else build_time_status_detail(state=binding.detail)
    return build_time_status(
        tool_key=binding.tool_key,
        state=summary,
        detail=detail,
    )


def create_time_status_runtime_module(binding: TimeStatusRuntimeBinding) -> WebModule:
    _require_binding(binding)
    host_id = time_status_runtime_host_id(binding.tool_key)
    store_id = system_kpi_store_id(binding.tool_key, TIME_STATUS_DESTINATION_KEY)

    def register_callbacks(dash_app: Dash, _services) -> None:
        @dash_app.callback(
            Output(host_id, 'children'),
            Input(store_id, 'data', allow_optional=True),
        )
        def refresh_time_status(store_data: object):
            return build_time_status_runtime_component(store_data, binding=binding)

    return WebModule(
        name='ada-time-status-runtime',
        register_callbacks=register_callbacks,
    )


def _require_binding(binding: object) -> None:
    if not isinstance(binding, TimeStatusRuntimeBinding):
        raise TypeError('binding must be TimeStatusRuntimeBinding')
