from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue

from .definitions import EspesadorDefinition, EspesadorMetricDefinition


@dataclass(frozen=True, slots=True)
# Punto de responsabilidad: EspesadorMetricReading; mantiene el mismo contrato que producción.
class EspesadorMetricReading:
    definition: EspesadorMetricDefinition
    value: DisplayValue


@dataclass(frozen=True, slots=True)
# Punto de responsabilidad: EspesadorReading; mantiene el mismo contrato que producción.
class EspesadorReading:
    definition: EspesadorDefinition
    state: DisplayValue
    feed: DisplayValue
    metrics: tuple[EspesadorMetricReading, ...]
