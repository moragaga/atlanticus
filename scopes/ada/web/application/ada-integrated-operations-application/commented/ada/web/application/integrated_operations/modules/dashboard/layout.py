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
    # Overview contiene simultáneamente Mina y Planta; el zoom cambia solo presentación CSS.
    return html.Section(
        [
            html.Div(
                [
                    build_mine_layout(),
                    build_plant_layout(),
                ],
                id=DASHBOARD_SCOPES_ID,
                className='ada-io-dashboard__scopes',
            ),
            _build_overview_controls(),
            _build_zoom_controls(),
        ],
        id=DASHBOARD_ROOT_ID,
        className='ada-io-dashboard',
        **{
            'data-ada-module': 'dashboard',
            'data-ada-io-presentation': 'overview',
        },
    )


def _build_overview_controls():
    # Estos controles no desmontan ningún scope; solo seleccionan qué porción se amplía.
    return html.Div(
        [
            _build_presentation_button(
                'MINA',
                target='mine',
                class_name='ada-io-dashboard__overview-control--mine',
                aria_label='Ampliar Mina',
            ),
            _build_presentation_button(
                'PLANTA',
                target='plant',
                class_name='ada-io-dashboard__overview-control--plant',
                aria_label='Ampliar Planta',
            ),
        ],
        className='ada-io-dashboard__overview-controls',
    )


def _build_zoom_controls():
    # En foco se puede volver a overview o cambiar directamente al scope opuesto.
    return html.Div(
        [
            _build_presentation_button(
                '×',
                target='overview',
                class_name='ada-io-dashboard__zoom-close',
                aria_label='Volver a vista general',
            ),
            _build_presentation_button(
                '‹ MINA',
                target='mine',
                class_name='ada-io-dashboard__zoom-side ada-io-dashboard__zoom-side--mine',
                aria_label='Cambiar a Mina',
            ),
            _build_presentation_button(
                'PLANTA ›',
                target='plant',
                class_name='ada-io-dashboard__zoom-side ada-io-dashboard__zoom-side--plant',
                aria_label='Cambiar a Planta',
            ),
        ],
        className='ada-io-dashboard__zoom-controls',
    )


def _build_presentation_button(
    label: str,
    *,
    target: str,
    class_name: str,
    aria_label: str,
):
    return html.Button(
        label,
        type='button',
        className=f'ada-io-dashboard__presentation-button {class_name}',
        **{
            'aria-label': aria_label,
            'data-ada-io-presentation-target': target,
        },
    )
