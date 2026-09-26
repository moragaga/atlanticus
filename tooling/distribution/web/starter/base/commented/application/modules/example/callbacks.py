from __future__ import annotations

# Los callbacks son propiedad del módulo y se registran mediante WebModule.

from dash import Input, Output
from dash import Dash

from atlanticus.web.services import ServiceRegistry


def register_callbacks(dash_app: Dash, _services: ServiceRegistry) -> None:
    @dash_app.callback(
        Output('starter-example-result', 'children'),
        Input('starter-example-button', 'n_clicks'),
    )
    def show_clicks(n_clicks: int | None) -> str:
        return f'Activations: {n_clicks or 0}'
