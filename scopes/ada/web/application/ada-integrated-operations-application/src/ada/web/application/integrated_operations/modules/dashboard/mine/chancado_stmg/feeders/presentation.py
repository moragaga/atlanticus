from __future__ import annotations

from collections.abc import Sequence

from dash import html
from dash.development.base_component import Component

from ada.web.ui.feeder import FeederValues, build_feeder_component

from .definitions import FeederKpiDefinition


def build_chancado_feeders(
    definitions: Sequence[FeederKpiDefinition],
    values: Sequence[FeederValues],
) -> Component:
    if len(definitions) != 4 or len(values) != len(definitions):
        raise ValueError('Chancado requires exactly four feeders')
    return html.Section(
        [
            html.Div(
                [
                    build_feeder_component(
                        definition.label,
                        reading,
                        inspection_key=definition.percent_kpi_key,
                    )
                    for definition, reading in zip(definitions, values, strict=True)
                ],
                className='ada-io-feeders__items',
            ),
            html.H3('FEEDERS', className='ada-io-feeders__title'),
        ],
        className='ada-io-feeders',
    )
