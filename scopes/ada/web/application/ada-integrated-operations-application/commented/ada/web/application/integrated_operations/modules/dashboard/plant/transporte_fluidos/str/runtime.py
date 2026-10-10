from __future__ import annotations

# Versión pedagógica: conserva literalmente la lógica y contratos del módulo productivo.


from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import (
    TRANSPORTE_FLUIDOS,
)
from ada.web.kpis.collector import component_kpi_store_id

from .ductos import map_str_ductos_store
from .espesadores import map_str_espesadores_store
from .overview import map_str_overview_store
from .presentation import build_str


# Solo el store del componente Transporte de Fluidos alimenta la card STR.
def register_str_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('str'), 'children'),
        Input(component_kpi_store_id(tool_key, TRANSPORTE_FLUIDOS.tool_component_key), 'data'),
    )
    def refresh_str(store_data: object):
        return build_str(
            map_str_overview_store(store_data),
            map_str_espesadores_store(store_data),
            map_str_ductos_store(store_data),
        )
