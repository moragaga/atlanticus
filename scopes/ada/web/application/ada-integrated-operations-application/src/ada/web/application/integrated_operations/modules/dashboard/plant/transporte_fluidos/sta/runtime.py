from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import (
    TRANSPORTE_FLUIDOS,
)
from ada.web.kpis.collector import component_kpi_store_id

from .mapper import map_sta_store
from .presentation import build_sta


def register_sta_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('sta'), 'children'),
        Input(component_kpi_store_id(tool_key, TRANSPORTE_FLUIDOS.tool_component_key), 'data'),
    )
    def refresh_sta(store_data: object):
        return build_sta(map_sta_store(store_data))
