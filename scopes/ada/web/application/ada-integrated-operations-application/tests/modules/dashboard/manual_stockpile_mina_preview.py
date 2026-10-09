from __future__ import annotations

from dash import Dash, Input, Output, dcc, html

from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.stockpile import (
    STOCKPILE_MINA_DEFINITIONS,
)
from ada.web.ui.display_status import DisplayValue
from ada.web.ui.stockpile import StockpileValues, build_stockpile_component


def _preview(pile_1_height: float, pile_2_height: float):
    values = (
        StockpileValues(DisplayValue.ok('65'), DisplayValue.ok(str(pile_1_height))),
        StockpileValues(DisplayValue.ok('80'), DisplayValue.ok(str(pile_2_height))),
    )
    return html.Div(
        [build_stockpile_component(definition, reading)
         for definition, reading in zip(STOCKPILE_MINA_DEFINITIONS, values, strict=True)],
        style={'display': 'flex', 'justifyContent': 'space-evenly', 'gap': '8px'},
    )


def main() -> None:
    app = Dash(__name__)
    app.title = 'Stockpile Mina'
    app.layout = html.Main(
        [
            html.Div(id='stockpile-preview', children=_preview(18, 23.5)),
            html.Label('Altura Pila 1 (m)'),
            dcc.Slider(0, 28, 0.5, value=18, id='stockpile-preview-height-1'),
            html.Label('Altura Pila 2 (m)'),
            dcc.Slider(0, 28, 0.5, value=23.5, id='stockpile-preview-height-2'),
        ],
        style={'maxWidth': '440px', 'margin': '3rem auto', 'padding': '1rem'},
    )

    @app.callback(
        Output('stockpile-preview', 'children'),
        Input('stockpile-preview-height-1', 'value'),
        Input('stockpile-preview-height-2', 'value'),
    )
    def refresh(pile_1_height: float, pile_2_height: float):
        return _preview(pile_1_height, pile_2_height)

    app.run(host='127.0.0.1', port=8057, debug=False)


if __name__ == '__main__':
    main()
