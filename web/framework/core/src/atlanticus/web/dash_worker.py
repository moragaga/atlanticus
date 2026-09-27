from __future__ import annotations

from dash import Dash


def prepare_dash_worker(dash: Dash) -> None:
    if not isinstance(dash, Dash):
        raise TypeError('Dash worker preparation requires a Dash instance')
    with dash.server.app_context():
        dash._generate_scripts_html()
        dash._generate_css_dist_html()
