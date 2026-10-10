from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
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
        Input(component_kpi_store_id(tool_key, PUERTO.tool_component_key), 'data'),
    )
    def refresh_puerto(store_data: object):
        readings, histories = decode_puerto_store(store_data)
        return build_puerto_component(
            map_puerto_readings(readings, histories),
            map_desaladora_readings(readings, histories),
        )
