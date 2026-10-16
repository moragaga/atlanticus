from __future__ import annotations

from dash.exceptions import PreventUpdate


def require_initial_delivery(store_data: object) -> None:
    if store_data is None:
        raise PreventUpdate
