from __future__ import annotations

# La primera revision latest es la barrera de inicio, no el contenido de cada destino.
# Un componente sin payload despues de la revision es un estado legitimo NOT_MAPPED.
# El modo de diseno sigue pudiendo construir placeholders directamente sin este callback.

from collections.abc import Mapping

from dash.exceptions import PreventUpdate


def require_initial_delivery(store_data: object, browser_revision: object) -> None:
    # El browser aun no ha confirmado una primera entrega latest del collector.
    if not isinstance(browser_revision, Mapping):
        raise PreventUpdate
    latest = browser_revision.get('latest')
    if not isinstance(latest, Mapping) or not isinstance(latest.get('revision'), str) or not latest['revision']:
        raise PreventUpdate
