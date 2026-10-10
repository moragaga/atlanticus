from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import MOLIENDA
from ada.web.kpis.collector import component_kpi_store_id

from .decoder import decode_molienda_store
from .overview import map_molienda_overview_readings
from .presentation import build_molienda
from .sags import map_molienda_sags_readings


# Un único callback consume el Store del componente y reutiliza el mismo paquete de lecturas para ambas secciones.
def register_molienda_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('molienda'), 'children'),
        Input(component_kpi_store_id(tool_key, MOLIENDA.tool_component_key), 'data'),
    )
    def refresh_molienda(store_data: object):
        readings, timeseries = decode_molienda_store(store_data)
        return build_molienda(
            map_molienda_overview_readings(readings, timeseries),
            map_molienda_sags_readings(readings),
        )
