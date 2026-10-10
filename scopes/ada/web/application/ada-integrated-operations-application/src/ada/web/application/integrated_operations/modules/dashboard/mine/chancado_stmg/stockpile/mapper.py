from __future__ import annotations

from collections.abc import Mapping

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.stockpile import StockpileValues

from .definitions import STOCKPILE_MINA_KPI_KEYS


def map_stockpile_mina_readings(
    readings: Mapping[str, DisplayValue],
) -> tuple[StockpileValues, ...]:
    return tuple(
        StockpileValues(
            percent=readings[percentage_key],
            height_m=readings[height_m_key],
        )
        for _, percentage_key, height_m_key in STOCKPILE_MINA_KPI_KEYS
    )
