from __future__ import annotations

from collections.abc import Sequence

from dash import html
from dash.development.base_component import Component

from .espesadores import EspesadorReading, build_espesadores
from .indicators import SelectivaIndicatorReading, build_selectiva_indicators


def build_selectiva(
    espesadores: Sequence[EspesadorReading],
    indicators: Sequence[SelectivaIndicatorReading],
) -> Component:
    return html.Section(
        [build_espesadores(espesadores), build_selectiva_indicators(indicators)],
        className='ada-io-selectiva',
    )
