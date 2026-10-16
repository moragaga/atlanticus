from __future__ import annotations

from dash.exceptions import PreventUpdate


# None indica que el collector aun no finalizo su primera lectura.
# Un store con ambas fuentes vacias es un resultado valido.
def require_initial_delivery(store_data: object) -> None:
    if store_data is None:
        raise PreventUpdate
