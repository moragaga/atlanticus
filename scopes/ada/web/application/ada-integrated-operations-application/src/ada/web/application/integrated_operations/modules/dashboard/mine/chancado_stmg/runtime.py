from __future__ import annotations

from dash import Input, Output, html

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import CHANCADO_STMG
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.ui.stockpile import build_stockpile_component

from .correas_stmg import (
    CORREAS_STMG_DEFINITIONS,
    CORREAS_STMG_METRIC,
    build_correas_stmg,
    map_correas_stmg_store,
)
from .equipos_ch import (
    EQUIPOS_CH_DEFINITIONS,
    FEEDERS_CH_DEFINITIONS,
    build_chancado_feeders,
    build_equipos_ch,
    map_equipos_ch_store,
    map_feeders_store,
)
from .produccion_global import build_produccion_global, map_produccion_global_store
from .stockpile_mina import STOCKPILE_MINA_DEFINITIONS, map_stockpile_mina_store


def register_chancado_stmg_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('chancado_stmg'), 'children'),
        Input(component_kpi_store_id(tool_key, CHANCADO_STMG.tool_component_key), 'data'),
    )
    def refresh_chancado_stmg(store_data: object):
        values = map_stockpile_mina_store(store_data)
        piles = [
            build_stockpile_component(definition, reading)
            for definition, reading in zip(STOCKPILE_MINA_DEFINITIONS, values, strict=True)
        ]
        return html.Div(
            [
                build_produccion_global(map_produccion_global_store(store_data)),
                build_equipos_ch(map_equipos_ch_store(store_data, EQUIPOS_CH_DEFINITIONS)),
                html.Div(
                    [
                        html.Div('Stockpile Mina', className='ada-io-stockpile__title'),
                        html.Div(piles, className='ada-io-stockpile-piles'),
                    ],
                    className='ada-io-stockpile',
                ),
                build_chancado_feeders(
                    FEEDERS_CH_DEFINITIONS,
                    map_feeders_store(store_data, FEEDERS_CH_DEFINITIONS),
                ),
                build_correas_stmg(
                    CORREAS_STMG_DEFINITIONS,
                    CORREAS_STMG_METRIC,
                    map_correas_stmg_store(
                        store_data, CORREAS_STMG_DEFINITIONS, CORREAS_STMG_METRIC
                    ),
                ),
            ],
            className='ada-io-chancado-stmg',
        )
