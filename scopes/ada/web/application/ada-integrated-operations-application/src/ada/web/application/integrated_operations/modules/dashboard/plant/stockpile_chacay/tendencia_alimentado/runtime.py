from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import (
    STOCKPILE_CHACAY,
)
from ada.web.kpis.collector import component_kpi_store_id

from .mapper import map_tendencia_alimentado_store
from .presentation import build_tendencia_alimentado


def register_tendencia_alimentado_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('tendencia_alimentado'), 'children'),
        Input(component_kpi_store_id(tool_key, STOCKPILE_CHACAY.tool_component_key), 'data'),
    )
    def refresh_tendencia_alimentado(store_data: object):
        return build_tendencia_alimentado(map_tendencia_alimentado_store(store_data))
