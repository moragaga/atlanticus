# Puente browser: consume el dcc.Store del Collector y reemplaza el host de Time Status.
from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING

from dash import Input, Output, html
from dash.exceptions import PreventUpdate
from dash.development.base_component import Component

from ada.web.kpis.collector import system_kpi_store_id
from ada.web.kpis.collector.presentation import DEFAULT_KPI_COLLECTOR_REVISION_STORE_ID
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
        **{'data-ada-time-status-runtime-host': 'true', 'data-ready': 'false'},
    )


def build_time_status_runtime_component(
    store_data: object,
    *,
    binding: TimeStatusRuntimeBinding,
    now_utc: datetime | None = None,
) -> Component:
    _require_binding(binding)
    summary = resolve_time_status_summary(store_data, binding=binding, now_utc=now_utc)
    # No vuelve a leer el Collector: reutiliza los estados ya resueltos.
    detail = build_time_status_detail(
        state=binding.resolve_detail(store_data),
        control_sources=summary.required_sources,
    )
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
            Output(host_id, 'data-ready'),
            Input(store_id, 'data', allow_optional=True),
            Input(DEFAULT_KPI_COLLECTOR_REVISION_STORE_ID, 'data'),
        )
        def refresh_time_status(store_data: object, browser_revision: object):
            if (
                not isinstance(browser_revision, Mapping)
                or browser_revision.get('initial_latest_state') not in {'ready', 'empty', 'error'}
            ):
                raise PreventUpdate
            return build_time_status_runtime_component(store_data, binding=binding), 'true'

    return WebModule(
        name='ada-time-status-runtime',
        register_callbacks=register_callbacks,
    )


def _require_binding(binding: object) -> None:
    if not isinstance(binding, TimeStatusRuntimeBinding):
        raise TypeError('binding must be TimeStatusRuntimeBinding')
