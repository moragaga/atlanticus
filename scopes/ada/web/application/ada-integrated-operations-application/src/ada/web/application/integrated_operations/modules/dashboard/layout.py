from dash import html

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    DASHBOARD_ROOT_ID,
    DASHBOARD_SCOPES_ID,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.layout import (
    build_mine_layout,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.layout import (
    build_plant_layout,
)


def build_dashboard_layout():
    return html.Section(
        html.Div(
            [
                build_mine_layout(),
                build_plant_layout(),
            ],
            id=DASHBOARD_SCOPES_ID,
            className='ada-io-dashboard__scopes',
        ),
        id=DASHBOARD_ROOT_ID,
        className='ada-io-dashboard',
        **{'data-ada-module': 'dashboard'},
    )
