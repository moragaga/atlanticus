from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import (
    STOCKPILE_CHACAY,
)
from ada.web.kpis.collector import component_kpi_store_id

from .mapper import map_stockpile_chacay_store
from .presentation import build_stockpile_chacay


def register_stockpile_chacay_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('stockpile_chacay'), 'children'),
        Input(component_kpi_store_id(tool_key, STOCKPILE_CHACAY.tool_component_key), 'data'),
    )
    def refresh_stockpile_chacay(store_data: object):
        return build_stockpile_chacay(map_stockpile_chacay_store(store_data))
