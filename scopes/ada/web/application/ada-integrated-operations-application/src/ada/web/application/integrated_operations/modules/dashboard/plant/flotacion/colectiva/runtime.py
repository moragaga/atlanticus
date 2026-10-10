from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.ids import dashboard_card_content_id
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import FLOTACION
from ada.web.kpis.collector import component_kpi_store_id

from .overview import map_colectiva_overview_store
from .presentation import build_colectiva
from .process import map_colectiva_process_store


def register_colectiva_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('colectiva'), 'children'),
        Input(component_kpi_store_id(tool_key, FLOTACION.tool_component_key), 'data'),
    )
    def refresh_colectiva(store_data: object):
        return build_colectiva(
            map_colectiva_overview_store(store_data),
            map_colectiva_process_store(store_data),
        )
