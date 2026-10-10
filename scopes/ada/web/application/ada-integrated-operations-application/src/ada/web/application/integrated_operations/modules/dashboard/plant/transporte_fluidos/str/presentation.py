from __future__ import annotations

from collections.abc import Sequence

from dash import html
from dash.development.base_component import Component

from .ductos import StrDuctReading, build_str_ductos
from .espesadores import StrEspesadorReading, build_str_espesadores
from .overview import StrOverviewReading, build_str_overview


def build_str(
    overview: StrOverviewReading,
    espesadores: Sequence[StrEspesadorReading],
    ductos: Sequence[StrDuctReading],
) -> Component:
    if not isinstance(overview, StrOverviewReading):
        raise TypeError('overview must be StrOverviewReading')
    return html.Section(
        [
            build_str_overview(overview),
            build_str_espesadores(espesadores),
            build_str_ductos(ductos),
        ],
        className='ada-io-str',
    )
