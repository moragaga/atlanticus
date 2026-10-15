from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.initial_readiness import require_initial_delivery
from ada.web.kpis.collector.presentation import DEFAULT_KPI_COLLECTOR_REVISION_STORE_ID

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
    dashboard_component_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import MOLIENDA
from ada.web.kpis.collector import component_kpi_store_id

from .decoder import decode_molienda_store
from .overview import map_molienda_overview_readings
from .presentation import build_molienda
from .sags import map_molienda_sags_readings


def register_molienda_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('molienda'), 'children'),
        Output(dashboard_component_id(MOLIENDA.key), 'data-ready'),
        Input(component_kpi_store_id(tool_key, MOLIENDA.tool_component_key), 'data'),
        Input(DEFAULT_KPI_COLLECTOR_REVISION_STORE_ID, 'data'),
    )
    def refresh_molienda(store_data: object, browser_revision: object):
        require_initial_delivery(store_data, browser_revision)
        readings, timeseries = decode_molienda_store(store_data)
        rendered = build_molienda(
            map_molienda_overview_readings(readings, timeseries),
            map_molienda_sags_readings(readings),
        )
        return rendered, 'true'
