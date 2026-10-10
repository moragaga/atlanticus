from __future__ import annotations

# Versión pedagógica: conserva literalmente la lógica y contratos del módulo productivo.


from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue

from .definitions import StrEspesadorDefinition, StrMetricDefinition


@dataclass(frozen=True, slots=True)
class StrMetricReading:
    definition: StrMetricDefinition
    value: DisplayValue


@dataclass(frozen=True, slots=True)
class StrEspesadorReading:
    definition: StrEspesadorDefinition
    state: DisplayValue
    feed: DisplayValue
    metrics: tuple[StrMetricReading, ...]
