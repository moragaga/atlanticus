from __future__ import annotations

from importlib.resources import files

from dash import Dash, Input, Output, dcc, html

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.stockpile import StockpileItem, StockpilePanel, build_stockpile_panel


def _height_text(height: float) -> str:
    return f'{height:g}'.replace('.', ',')


def _preview(pile_1_height: float, pile_2_height: float):
    return build_stockpile_panel(
        StockpilePanel(
            items=(
                StockpileItem(
                    key='pila_1',
                    label='Pila 1',
                    percentage=DisplayValue.ok('65'),
                    height_m=DisplayValue.ok(_height_text(pile_1_height)),
                ),
                StockpileItem(
                    key='pila_2',
                    label='Pila 2',
                    percentage=DisplayValue.ok('80'),
                    height_m=DisplayValue.ok(_height_text(pile_2_height)),
                ),
            ),
            scale_max_m=28,
        )
    )


def main() -> None:
    assets = files('ada.web.ui.stockpile').joinpath('resources/css')
    app = Dash(__name__, assets_folder=str(assets))
    app.title = 'Stockpile Mina — Visual Preview'
    app.layout = html.Main(
        [
            html.H3('Stockpile Mina — preview local'),
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
