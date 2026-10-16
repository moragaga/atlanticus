from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.initial_readiness import require_initial_delivery

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
    dashboard_component_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import CARGUIO
from ada.web.kpis.collector import component_kpi_store_id

from .carguio_global_turno import map_carguio_global_turno_readings
from .decoder import decode_carguio_store
from .equipos_servicio import map_equipos_servicio_readings
from .gestion_carguio_turno import map_gestion_carguio_turno_readings
from .presentation import build_carguio


def register_carguio_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('carguio_global_turno'), 'children'),
        Output(dashboard_card_content_id('equipos_servicio'), 'children'),
        Output(dashboard_card_content_id('gestion_carguio_turno'), 'children'),
        Output(dashboard_component_id(CARGUIO.key), 'data-ready'),
        Input(component_kpi_store_id(tool_key, CARGUIO.tool_component_key), 'data'),
    )
    def refresh_carguio(store_data: object):
        require_initial_delivery(store_data)
        values = decode_carguio_store(store_data)
        rendered = build_carguio(
            carguio_global_turno=map_carguio_global_turno_readings(values),
            equipos_servicio=map_equipos_servicio_readings(values),
            gestion_carguio_turno=map_gestion_carguio_turno_readings(values),
        )
        return (*rendered, 'true')
