from __future__ import annotations

# La barrera de inicio confirma que el collector completo su primera lectura.
# La ausencia de documento y los errores son resultados terminales, no espera infinita.
# El modo de diseno sigue pudiendo construir placeholders directamente sin este callback.

from collections.abc import Mapping

from dash.exceptions import PreventUpdate


def require_initial_delivery(
    store_data: object, browser_revision: object,
    presentation_mode: object,
) -> None:
    # La confirmación proviene del runtime que lee Cosmos, no de la presencia de valores.
    # Authoring muestra estados de prueba sin requerir la entrega operativa.
    if presentation_mode == 'authoring':
        return
    # El revision store central ya contiene la resolucion inicial KPI.
    if (
        not isinstance(browser_revision, Mapping)
        or browser_revision.get('initial_latest_state') not in {'ready', 'empty', 'error'}
    ):
        raise PreventUpdate
