from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import FLOTACION
from ada.web.kpis.collector import component_kpi_store_id

from .espesadores import map_espesadores_store
from .indicators import map_selectiva_indicators_store
from .presentation import build_selectiva


# Ambas partes de Selectiva consumen el mismo store de Flotación.
def register_selectiva_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('selectiva'), 'children'),
        Input(component_kpi_store_id(tool_key, FLOTACION.tool_component_key), 'data'),
    )
    def refresh_selectiva(store_data: object):
        return build_selectiva(
            map_espesadores_store(store_data),
            map_selectiva_indicators_store(store_data),
        )
