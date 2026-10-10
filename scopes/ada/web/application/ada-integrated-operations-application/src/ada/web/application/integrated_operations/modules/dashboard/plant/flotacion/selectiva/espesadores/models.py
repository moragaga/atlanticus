from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue

from .definitions import EspesadorDefinition, EspesadorMetricDefinition


@dataclass(frozen=True, slots=True)
class EspesadorMetricReading:
    definition: EspesadorMetricDefinition
    value: DisplayValue


@dataclass(frozen=True, slots=True)
class EspesadorReading:
    definition: EspesadorDefinition
    state: DisplayValue
    feed: DisplayValue
    metrics: tuple[EspesadorMetricReading, ...]
