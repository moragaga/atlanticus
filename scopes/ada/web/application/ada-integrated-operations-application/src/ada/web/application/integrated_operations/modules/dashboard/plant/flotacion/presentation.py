from __future__ import annotations

from collections.abc import Sequence

from dash.development.base_component import Component

from .colectiva.overview import ColectivaOverviewReading
from .colectiva.presentation import build_colectiva
from .colectiva.process import ColectivaProcessReading
from .selectiva.espesadores import EspesadorReading
from .selectiva.indicators import SelectivaIndicatorReading
from .selectiva.presentation import build_selectiva


def build_flotacion(
    overview: ColectivaOverviewReading,
    process: ColectivaProcessReading,
    espesadores: Sequence[EspesadorReading],
    indicators: Sequence[SelectivaIndicatorReading],
) -> tuple[Component, Component]:
    return build_colectiva(overview, process), build_selectiva(espesadores, indicators)
