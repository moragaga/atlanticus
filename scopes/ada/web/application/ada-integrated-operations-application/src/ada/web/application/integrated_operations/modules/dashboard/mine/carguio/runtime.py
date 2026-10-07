from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import CARGUIO
from ada.web.kpis.collector import component_kpi_store_id

from .carguio_global_turno import (
    build_carguio_global_turno,
    map_carguio_global_turno_store,
)
from .equipos_servicio import (
    build_equipos_servicio,
    map_equipos_servicio_store,
)


def register_carguio_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('carguio_global_turno'), 'children'),
        Output(dashboard_card_content_id('equipos_servicio'), 'children'),
        Input(component_kpi_store_id(tool_key, CARGUIO.tool_component_key), 'data'),
    )
    def refresh_carguio(store_data: object):
        global_state, global_source_status = map_carguio_global_turno_store(
            store_data
        )
        equipos_state, equipos_source_status = map_equipos_servicio_store(
            store_data
        )
        return (
            build_carguio_global_turno(global_state, global_source_status),
            build_equipos_servicio(equipos_state, equipos_source_status),
        )
