from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.initial_readiness import require_initial_delivery

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
    dashboard_component_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import (
    TRANSPORTE,
)
from ada.web.kpis.collector import component_kpi_store_id

from .decoder import decode_transporte_store
from .numero_operativo_turno import map_numero_operativo_turno_readings
from .presentation import build_transporte
from .transporte_global_turno import map_transporte_global_turno_readings


def register_transporte_callback(dash_app, *, tool_key: str) -> None:
    # La señal forma parte del mismo resultado del render para evitar carreras.
    # No depende de que el collector haya publicado datos definitivos.
    @dash_app.callback(
        Output(dashboard_card_content_id('transporte_global'), 'children'),
        Output(dashboard_card_content_id('numero_operativo'), 'children'),
        Output(dashboard_component_id(TRANSPORTE.key), 'data-ready'),
        Input(component_kpi_store_id(tool_key, TRANSPORTE.tool_component_key), 'data'),
    )
    def refresh_transporte(store_data: object):
        # La primera lectura habilita el store; sin revision KPI global.
        require_initial_delivery(store_data)
        values = decode_transporte_store(store_data)
        rendered = build_transporte(
            transporte_global_turno=map_transporte_global_turno_readings(values),
            numero_operativo_turno=map_numero_operativo_turno_readings(values),
        )
        # Preservamos el orden de las tarjetas y agregamos el marcador del área.
        return (*rendered, 'true')
