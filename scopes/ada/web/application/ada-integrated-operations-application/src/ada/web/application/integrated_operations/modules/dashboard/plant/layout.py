from dash import html

from ada.web.application.integrated_operations.modules.dashboard.card import (
    build_component_panel,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import (
    FLOTACION,
    MOLIENDA,
    PUERTO,
    STOCKPILE_CHACAY,
    TRANSPORTE_FLUIDOS,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.ids import (
    PLANT_CONTENT_ID,
    PLANT_ROOT_ID,
)


def build_plant_layout():
    return html.Section(
        html.Div(
            [
                build_component_panel(STOCKPILE_CHACAY),
                build_component_panel(MOLIENDA),
                build_component_panel(FLOTACION),
                build_component_panel(TRANSPORTE_FLUIDOS),
                build_component_panel(PUERTO),
            ],
            id=PLANT_CONTENT_ID,
            className='ada-io-scope__content ada-io-plant-grid',
        ),
        id=PLANT_ROOT_ID,
        className='ada-io-scope ada-io-scope--plant',
        **{
            'aria-label': 'Planta',
            'data-ada-operational-scope': 'plant',
        },
    )
