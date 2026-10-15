from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.initial_readiness import require_initial_delivery
from ada.web.kpis.collector.presentation import DEFAULT_KPI_COLLECTOR_REVISION_STORE_ID

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
    dashboard_component_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import FLOTACION
from ada.web.kpis.collector import component_kpi_store_id

from .colectiva.overview import map_colectiva_overview_readings
from .colectiva.process import map_colectiva_process_readings
from .decoder import decode_flotacion_store
from .presentation import build_flotacion
from .selectiva.espesadores import map_espesadores_readings
from .selectiva.indicators import map_selectiva_indicators_readings


def register_flotacion_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('colectiva'), 'children'),
        Output(dashboard_card_content_id('selectiva'), 'children'),
        Output(dashboard_component_id(FLOTACION.key), 'data-ready'),
        Input(component_kpi_store_id(tool_key, FLOTACION.tool_component_key), 'data'),
        Input(DEFAULT_KPI_COLLECTOR_REVISION_STORE_ID, 'data'),
    )
    def refresh_flotacion(store_data: object, browser_revision: object):
        require_initial_delivery(store_data, browser_revision)
        readings, timeseries = decode_flotacion_store(store_data)
        rendered = build_flotacion(
            map_colectiva_overview_readings(readings, timeseries),
            map_colectiva_process_readings(readings),
            map_espesadores_readings(readings),
            map_selectiva_indicators_readings(readings),
        )
        return (*rendered, 'true')
