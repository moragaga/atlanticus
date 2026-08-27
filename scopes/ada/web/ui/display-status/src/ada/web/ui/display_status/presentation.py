from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from .models import DisplayStatus, resolve_status_visual


def build_display_status_icon(
    status: DisplayStatus,
    *,
    class_name: str | None = None,
) -> Component | None:
    visual = resolve_status_visual(status)
    if visual is None:
        return None

    classes = ' '.join(
        part
        for part in ('ada-display-status__icon', class_name)
        if part is not None and part.strip()
    )
    return html.Img(
        src=visual.asset_url,
        alt=visual.alt,
        title=visual.title,
        className=classes,
    )
