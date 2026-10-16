from __future__ import annotations

from collections.abc import Mapping

from dash.exceptions import PreventUpdate


def require_initial_delivery(store_data: object, browser_revision: object) -> None:
    if (
        not isinstance(browser_revision, Mapping)
        or browser_revision.get('initial_latest_state') not in {'ready', 'empty', 'error'}
    ):
        raise PreventUpdate
