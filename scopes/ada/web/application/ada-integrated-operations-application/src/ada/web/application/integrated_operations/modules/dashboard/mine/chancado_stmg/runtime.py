from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import CHANCADO_STMG
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.kpis.readings import read_component_latest

from .correas_stmg import (
    CORREAS_STMG_DEFINITIONS,
    CORREAS_STMG_METRIC,
    map_correas_stmg_store,
)
from .equipos_ch import EQUIPOS_CH_DEFINITIONS, map_equipos_ch_store
from .feeders import FEEDERS_CH_DEFINITIONS, map_feeders_store
from .leyes import map_leyes_store
from .presentation import build_chancado_stmg
from .produccion_global import map_produccion_global_store
from .stockpile import map_stockpile_mina_store


def register_chancado_stmg_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('chancado_stmg'), 'children'),
        Input(component_kpi_store_id(tool_key, CHANCADO_STMG.tool_component_key), 'data'),
    )
    def refresh_chancado_stmg(store_data: object):
        readings = read_component_latest(store_data)
        return build_chancado_stmg(
            produccion_global=map_produccion_global_store(readings),
            equipos_ch=map_equipos_ch_store(readings, EQUIPOS_CH_DEFINITIONS),
            stockpile_mina=map_stockpile_mina_store(readings),
            feeders=map_feeders_store(readings, FEEDERS_CH_DEFINITIONS),
            correas_stmg=map_correas_stmg_store(
                readings, CORREAS_STMG_DEFINITIONS, CORREAS_STMG_METRIC
            ),
            leyes=map_leyes_store(readings),
        )
