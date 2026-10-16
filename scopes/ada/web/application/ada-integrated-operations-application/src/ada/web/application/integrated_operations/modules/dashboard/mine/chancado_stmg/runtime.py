from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.initial_readiness import require_initial_delivery

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
    dashboard_component_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import CHANCADO_STMG
from ada.web.kpis.collector import component_kpi_store_id

from .correas_stmg import (
    CORREAS_STMG_DEFINITIONS,
    CORREAS_STMG_METRIC,
    map_correas_stmg_readings,
)
from .decoder import decode_chancado_stmg_store
from .equipos_ch import EQUIPOS_CH_DEFINITIONS, map_equipos_ch_readings
from .feeders import FEEDERS_CH_DEFINITIONS, map_feeders_readings
from .leyes import map_leyes_readings
from .presentation import build_chancado_stmg
from .produccion_global import map_produccion_global_readings
from .stockpile import map_stockpile_mina_readings


def register_chancado_stmg_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('chancado_stmg'), 'children'),
        Output(dashboard_component_id(CHANCADO_STMG.key), 'data-ready'),
        Input(component_kpi_store_id(tool_key, CHANCADO_STMG.tool_component_key), 'data'),
    )
    def refresh_chancado_stmg(store_data: object):
        require_initial_delivery(store_data)
        readings = decode_chancado_stmg_store(store_data)
        rendered = build_chancado_stmg(
            produccion_global=map_produccion_global_readings(readings),
            equipos_ch=map_equipos_ch_readings(readings, EQUIPOS_CH_DEFINITIONS),
            stockpile_mina=map_stockpile_mina_readings(readings),
            feeders=map_feeders_readings(readings, FEEDERS_CH_DEFINITIONS),
            correas_stmg=map_correas_stmg_readings(
                readings, CORREAS_STMG_DEFINITIONS, CORREAS_STMG_METRIC
            ),
            leyes=map_leyes_readings(readings),
        )
        return rendered, 'true'
