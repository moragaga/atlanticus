# Compone la vista y preserva las claves KPI inspeccionables.
from __future__ import annotations

from collections.abc import Sequence

from dash import html
from dash.development.base_component import Component

from .overview import MoliendaOverviewReading, build_molienda_overview
from .sags import MoliendaLineReading, build_molienda_sags


def build_molienda(
    overview: MoliendaOverviewReading,
    lines: Sequence[MoliendaLineReading],
) -> Component:
    if not isinstance(overview, MoliendaOverviewReading):
        raise TypeError('overview must be MoliendaOverviewReading')
    if not isinstance(lines, Sequence) or not all(
        isinstance(line, MoliendaLineReading) for line in lines
    ):
        raise TypeError('lines must be a sequence of MoliendaLineReading')
    return html.Section(
        [build_molienda_overview(overview), build_molienda_sags(lines)],
        className='ada-io-molienda',
    )
