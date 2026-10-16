from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.initial_readiness import require_initial_delivery

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
    dashboard_component_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import PUERTO
from ada.web.kpis.collector import component_kpi_store_id

from .decoder import decode_puerto_store
from .desaladora import map_desaladora_readings
from .presentation import build_puerto_component
from .puerto import map_puerto_readings


def register_puerto_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('puerto'), 'children'),
        Output(dashboard_card_content_id('desaladora'), 'children'),
        Output(dashboard_component_id(PUERTO.key), 'data-ready'),
        Input(component_kpi_store_id(tool_key, PUERTO.tool_component_key), 'data'),
    )
    def refresh_puerto(store_data: object):
        require_initial_delivery(store_data)
        readings, histories = decode_puerto_store(store_data)
        rendered = build_puerto_component(
            map_puerto_readings(readings, histories),
            map_desaladora_readings(readings, histories),
        )
        return (*rendered, 'true')
