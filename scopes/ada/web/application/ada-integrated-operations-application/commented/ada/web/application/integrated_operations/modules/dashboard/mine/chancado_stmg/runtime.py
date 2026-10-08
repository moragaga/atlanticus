# Callback ADA: lee el Store y compone dos pilas individuales sin lógica en Stockpile.
from __future__ import annotations

from dash import Input, Output, html

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import CHANCADO_STMG
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.ui.stockpile import build_stockpile_component

from .stockpile_mina import STOCKPILE_MINA_DEFINITIONS, map_stockpile_mina_store


def register_chancado_stmg_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('chancado_stmg'), 'children'),
        Input(component_kpi_store_id(tool_key, CHANCADO_STMG.tool_component_key), 'data'),
    )
    def refresh_chancado_stmg(store_data: object):
        values = map_stockpile_mina_store(store_data)
        return html.Div(
            [
                build_stockpile_component(definition, reading)
                for definition, reading in zip(STOCKPILE_MINA_DEFINITIONS, values, strict=True)
            ],
            className='ada-io-stockpile-piles',
        )
