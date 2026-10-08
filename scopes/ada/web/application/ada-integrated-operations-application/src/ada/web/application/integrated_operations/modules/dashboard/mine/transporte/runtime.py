from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import (
    TRANSPORTE,
)
from ada.web.kpis.collector import component_kpi_store_id

from .numero_operativo_turno import (
    build_numero_operativo_turno,
    map_numero_operativo_turno_store,
)
from .transporte_global_turno import (
    build_transporte_global_turno,
    map_transporte_global_turno_store,
)


def register_transporte_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('transporte_global'), 'children'),
        Output(dashboard_card_content_id('numero_operativo'), 'children'),
        Input(
            component_kpi_store_id(
                tool_key,
                TRANSPORTE.tool_component_key,
            ),
            'data',
        ),
    )
    def refresh_transporte(store_data: object):
        global_state, global_source_status = map_transporte_global_turno_store(
            store_data
        )
        numero_state, numero_source_status = map_numero_operativo_turno_store(
            store_data
        )
        return (
            build_transporte_global_turno(global_state, global_source_status),
            build_numero_operativo_turno(numero_state, numero_source_status),
        )
