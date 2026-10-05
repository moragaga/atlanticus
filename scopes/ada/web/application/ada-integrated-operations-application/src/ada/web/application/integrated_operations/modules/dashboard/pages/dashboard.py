from dash import register_page

from ada.web.application.integrated_operations.modules.dashboard.layout import (
    build_dashboard_layout,
)

register_page(__name__, path='/', name='Dashboard', order=0)

layout = build_dashboard_layout
