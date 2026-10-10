from __future__ import annotations

from collections.abc import Sequence

from dash.development.base_component import Component

from .indicators import FluidMetricReading
from .sta import build_sta
from .stc import StcReading, build_stc
from .str.ductos import StrDuctReading
from .str.espesadores import StrEspesadorReading
from .str.overview import StrOverviewReading
from .str.presentation import build_str
from .tranque import build_tranque


def build_transporte_fluidos(
    overview: StrOverviewReading,
    espesadores: Sequence[StrEspesadorReading],
    ductos: Sequence[StrDuctReading],
    stc: StcReading,
    tranque: Sequence[FluidMetricReading],
    sta: Sequence[FluidMetricReading],
) -> tuple[Component, Component, Component, Component]:
    return (
        build_str(overview, espesadores, ductos),
        build_stc(stc),
        build_tranque(tranque),
        build_sta(sta),
    )
