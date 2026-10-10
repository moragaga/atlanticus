# El mapper interpreta posición y filas ya preparadas; Feeders comparte el mismo diccionario.
from __future__ import annotations

from collections.abc import Mapping

from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.stockpile import StockpileValues

from ..feeders import map_chacay_feeders_readings
from .definitions import (
    STOCKPILE_CHACAY_PILES,
    STOCKPILE_CHACAY_POSITION_KEY,
    STOCKPILE_CHACAY_POSITIONS,
    STOCKPILE_CHACAY_ROWS,
)
from .models import ChacayMetric, StockpileChacayState


def map_stockpile_chacay_readings(readings: Mapping[str, DisplayValue]) -> StockpileChacayState:
    position = readings[STOCKPILE_CHACAY_POSITION_KEY]
    if position.status is DisplayStatus.OK:
        number = str(position.value).strip()
        if number not in {str(value) for value in STOCKPILE_CHACAY_POSITIONS}:
            position = DisplayValue.invalid()
        else:
            position = DisplayValue.ok(int(number))
    return StockpileChacayState(
        position=position,
        piles=tuple(
            StockpileValues(percent=readings[definition.kpi_key])
            for definition in STOCKPILE_CHACAY_PILES
        ),
        feeders=map_chacay_feeders_readings(readings),
        rows=tuple(
            ChacayMetric(
                key=definition.key,
                label=definition.label,
                kpi_key=definition.kpi_key,
                value=readings[definition.kpi_key],
            )
            for definition in STOCKPILE_CHACAY_ROWS
        ),
    )
