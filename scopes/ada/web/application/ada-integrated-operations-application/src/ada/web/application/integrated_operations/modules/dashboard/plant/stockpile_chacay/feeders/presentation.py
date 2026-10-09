from __future__ import annotations

from decimal import Decimal

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, build_display_status_icon
from ada.web.ui.feeder import FeederColor

from .definitions import STOCKPILE_CHACAY_FEEDER_GROUPS, ChacayFeederDefinition
from .models import ChacayFeederReading


def build_chacay_feeders(
    groups: tuple[tuple[ChacayFeederReading, ...], ...],
    definitions: tuple[tuple[ChacayFeederDefinition, ...], ...] = STOCKPILE_CHACAY_FEEDER_GROUPS,
) -> Component:
    return html.Div(
        [
            html.Div(
                [
                    _feeder(definition, reading)
                    for definition, reading in zip(group_definitions, group_readings, strict=True)
                ],
                className='ada-io-chacay-feeders__group',
            )
            for group_definitions, group_readings in zip(definitions, groups, strict=True)
        ],
        className='ada-io-chacay-feeders',
    )


def _feeder(definition: ChacayFeederDefinition, reading: ChacayFeederReading) -> Component:
    if reading.value.status is DisplayStatus.OK:
        height = min(reading.value.value, Decimal('100'))
        graphic = html.Div(
            html.Div(
                className=_fill_class(reading.color),
                style={'height': f'{height}%'},
            ),
            className='ada-io-chacay-feeders__bar',
        )
    else:
        graphic = build_display_status_icon(
            reading.value.status,
            class_name='ada-io-chacay-feeders__status-icon',
        )
    return html.Div(
        graphic,
        className='ada-io-chacay-feeders__feeder',
        role='button',
        tabIndex=0,
        title=definition.value_kpi_key,
        **{'data-kpi-inspection-key': definition.value_kpi_key},
    )


def _fill_class(color: FeederColor | None) -> str:
    suffix = color.value if color is not None else FeederColor.NEUTRAL.value
    return f'ada-io-chacay-feeders__fill ada-io-chacay-feeders__fill--{suffix}'
