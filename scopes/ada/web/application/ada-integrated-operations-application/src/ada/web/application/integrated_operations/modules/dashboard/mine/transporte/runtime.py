from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import (
    TRANSPORTE,
)
from ada.web.kpis.collector import component_kpi_store_id

from .transporte_global_turno import (
    build_transporte_global_turno,
    map_transporte_global_turno_store,
)


def register_transporte_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('transporte_global'), 'children'),
        Input(
            component_kpi_store_id(
                tool_key,
                TRANSPORTE.tool_component_key,
            ),
            'data',
        ),
    )
    def refresh_transporte(store_data: object):
        state, source_status = map_transporte_global_turno_store(store_data)
        return build_transporte_global_turno(state, source_status)
