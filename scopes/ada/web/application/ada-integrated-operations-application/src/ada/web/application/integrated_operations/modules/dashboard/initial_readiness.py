from __future__ import annotations

from collections.abc import Mapping

from dash.exceptions import PreventUpdate


def require_initial_delivery(store_data: object, browser_revision: object) -> None:
    if not isinstance(browser_revision, Mapping):
        raise PreventUpdate
    latest = browser_revision.get('latest')
    if not isinstance(latest, Mapping) or not isinstance(latest.get('revision'), str) or not latest['revision']:
        raise PreventUpdate
