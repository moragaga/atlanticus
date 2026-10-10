# Versión pedagógica: Los cuatro Outputs consumen el mismo conjunto de lecturas preparado desde un único Store.
from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import (
    TRANSPORTE_FLUIDOS,
)
from ada.web.kpis.collector import component_kpi_store_id

from .decoder import decode_transporte_fluidos_store
from .presentation import build_transporte_fluidos
from .sta import map_sta_readings
from .stc import map_stc_readings
from .str.ductos import map_str_ductos_readings
from .str.espesadores import map_str_espesadores_readings
from .str.overview import map_str_overview_readings
from .tranque import map_tranque_readings


def register_transporte_fluidos_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('str'), 'children'),
        Output(dashboard_card_content_id('stc'), 'children'),
        Output(dashboard_card_content_id('tranque'), 'children'),
        Output(dashboard_card_content_id('sta'), 'children'),
        Input(component_kpi_store_id(tool_key, TRANSPORTE_FLUIDOS.tool_component_key), 'data'),
    )
    def refresh_transporte_fluidos(store_data: object):
        readings = decode_transporte_fluidos_store(store_data)
        return build_transporte_fluidos(
            map_str_overview_readings(readings, store_data),
            map_str_espesadores_readings(readings),
            map_str_ductos_readings(readings),
            map_stc_readings(readings),
            map_tranque_readings(readings),
            map_sta_readings(readings),
        )
