from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import (
    STOCKPILE_CHACAY,
)
from ada.web.kpis.collector import component_kpi_store_id

from .decoder import decode_stockpile_chacay_store
from .presentation import build_stockpile_chacay_cards
from .stockpile import map_stockpile_chacay_readings
from .tendencia_alimentado import map_tendencia_alimentado_readings


def register_stockpile_chacay_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('stockpile_chacay'), 'children'),
        Output(dashboard_card_content_id('tendencia_alimentado'), 'children'),
        Input(component_kpi_store_id(tool_key, STOCKPILE_CHACAY.tool_component_key), 'data'),
    )
    def refresh_stockpile_chacay(store_data: object):
        readings, timeseries = decode_stockpile_chacay_store(store_data)
        return build_stockpile_chacay_cards(
            stockpile=map_stockpile_chacay_readings(readings),
            tendencia=map_tendencia_alimentado_readings(readings, timeseries),
        )
