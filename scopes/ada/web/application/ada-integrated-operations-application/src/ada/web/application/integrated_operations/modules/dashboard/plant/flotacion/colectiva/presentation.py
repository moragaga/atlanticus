from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from .overview import ColectivaOverviewReading, build_colectiva_overview
from .process import ColectivaProcessReading, build_colectiva_process


def build_colectiva(
    overview: ColectivaOverviewReading,
    process: ColectivaProcessReading,
) -> Component:
    if not isinstance(overview, ColectivaOverviewReading):
        raise TypeError('overview must be ColectivaOverviewReading')
    if not isinstance(process, ColectivaProcessReading):
        raise TypeError('process must be ColectivaProcessReading')
    return html.Section(
        [build_colectiva_overview(overview), build_colectiva_process(process)],
        className='ada-io-colectiva',
    )
