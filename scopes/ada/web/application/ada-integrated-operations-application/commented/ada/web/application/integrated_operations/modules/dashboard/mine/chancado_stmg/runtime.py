# Callback ADA: utiliza el Store existente; el encabezado y la cuadrícula pertenecen al consumidor, no al componente Stockpile.
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
        piles = [
            build_stockpile_component(definition, reading)
            for definition, reading in zip(STOCKPILE_MINA_DEFINITIONS, values, strict=True)
        ]
        return html.Div(
            [
                html.Div('Stockpile Mina', className='ada-io-stockpile__title'),
                html.Div(piles, className='ada-io-stockpile-piles'),
            ],
            className='ada-io-stockpile',
        )
