from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.stockpile import StockpileValues

from .feeders.models import ChacayFeederReading


@dataclass(frozen=True, slots=True)
class ChacayMetric:
    key: str
    label: str
    kpi_key: str
    value: DisplayValue


@dataclass(frozen=True, slots=True)
class StockpileChacayState:
    position: DisplayValue
    piles: tuple[StockpileValues, ...]
    feeders: tuple[tuple[ChacayFeederReading, ...], ...]
    rows: tuple[ChacayMetric, ...]
