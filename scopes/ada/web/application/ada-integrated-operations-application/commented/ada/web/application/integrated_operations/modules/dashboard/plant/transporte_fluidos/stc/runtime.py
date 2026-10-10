from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import (
    TRANSPORTE_FLUIDOS,
)
from ada.web.kpis.collector import component_kpi_store_id

from .mapper import map_stc_store
from .presentation import build_stc


# Explicación: este bloque implementa la misma responsabilidad que su par productivo.
def register_stc_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('stc'), 'children'),
        Input(component_kpi_store_id(tool_key, TRANSPORTE_FLUIDOS.tool_component_key), 'data'),
    )
    def refresh_stc(store_data: object):
        return build_stc(map_stc_store(store_data))
