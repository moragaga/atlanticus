from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.level_gauge import LevelGaugeView

from ..indicators import FluidMetricReading
from .definitions import StcEspesadorDefinition


# El modelo de dominio mantiene el mismo tipo de lectura procedente del submódulo de indicadores.
@dataclass(frozen=True, slots=True)
class StcEspesadorReading:
    definition: StcEspesadorDefinition
    state: DisplayValue
    feed: DisplayValue
    metrics: tuple[FluidMetricReading, ...]


@dataclass(frozen=True, slots=True)
class StcReading:
    indicators: tuple[FluidMetricReading, ...]
    espesador: StcEspesadorReading
    levels: tuple[LevelGaugeView, ...]
