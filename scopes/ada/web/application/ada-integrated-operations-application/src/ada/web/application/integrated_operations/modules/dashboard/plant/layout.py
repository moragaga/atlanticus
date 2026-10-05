from dash import html

from ada.web.application.integrated_operations.modules.dashboard.plant.ids import (
    PLANT_CONTENT_ID,
    PLANT_ROOT_ID,
)


def build_plant_layout():
    return html.Section(
        [
            html.H2('Planta', className='ada-io-scope__title'),
            html.Div(id=PLANT_CONTENT_ID, className='ada-io-scope__content'),
        ],
        id=PLANT_ROOT_ID,
        className='ada-io-scope ada-io-scope--plant',
        **{'data-ada-operational-scope': 'plant'},
    )
