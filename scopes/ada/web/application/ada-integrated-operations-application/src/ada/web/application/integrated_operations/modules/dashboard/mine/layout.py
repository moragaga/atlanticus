from dash import html

from ada.web.application.integrated_operations.modules.dashboard.mine.ids import (
    MINE_CONTENT_ID,
    MINE_ROOT_ID,
)


def build_mine_layout():
    return html.Section(
        [
            html.H2('Mina', className='ada-io-scope__title'),
            html.Div(id=MINE_CONTENT_ID, className='ada-io-scope__content'),
        ],
        id=MINE_ROOT_ID,
        className='ada-io-scope ada-io-scope--mine',
        **{'data-ada-operational-scope': 'mine'},
    )
