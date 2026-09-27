from __future__ import annotations

from dash import Dash


# Registrar recursos compartibles antes de servir peticiones; no ejecutar layouts
# de usuarios ni simular identidades para el calentamiento de producción.
def prepare_dash_worker(dash: Dash) -> None:
    if not isinstance(dash, Dash):
        raise TypeError('Dash worker preparation requires a Dash instance')
    # Usar el contexto Flask existente sin disparar una solicitud HTTP artificial.
    with dash.server.app_context():
        dash._generate_scripts_html()
        dash._generate_css_dist_html()
