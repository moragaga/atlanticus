from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.level_gauge import LevelGaugeView

from ..metrics import FluidMetricReading
from .definitions import StcEspesadorDefinition


@dataclass(frozen=True, slots=True)
# Explicación: este bloque implementa la misma responsabilidad que su par productivo.
class StcEspesadorReading:
    definition: StcEspesadorDefinition
    state: DisplayValue
    feed: DisplayValue
    metrics: tuple[FluidMetricReading, ...]


@dataclass(frozen=True, slots=True)
# Explicación: este bloque implementa la misma responsabilidad que su par productivo.
class StcReading:
    indicators: tuple[FluidMetricReading, ...]
    espesador: StcEspesadorReading
    levels: tuple[LevelGaugeView, ...]
