from dash import html

from ada.web.application.integrated_operations.modules.dashboard.card import (
    build_component_panel,
    build_shared_dashboard_card,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import (
    CARGUIO,
    CARGUIO_TRANSPORTE,
    CHANCADO_STMG,
    GENERAL_MINA,
    TRANSPORTE,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.ids import (
    MINE_CONTENT_ID,
    MINE_ROOT_ID,
)


def build_mine_layout():
    return html.Section(
        html.Div(
            [
                build_component_panel(GENERAL_MINA),
                build_component_panel(CARGUIO),
                build_component_panel(TRANSPORTE),
                html.Div(
                    build_shared_dashboard_card(CARGUIO_TRANSPORTE),
                    className='ada-io-mine-grid__shared-card',
                ),
                build_component_panel(CHANCADO_STMG),
            ],
            id=MINE_CONTENT_ID,
            className='ada-io-scope__content ada-io-mine-grid',
        ),
        id=MINE_ROOT_ID,
        className='ada-io-scope ada-io-scope--mine',
        **{
            'aria-label': 'Mina',
            'data-ada-operational-scope': 'mine',
        },
    )
