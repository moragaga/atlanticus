from __future__ import annotations

from ada.web.kpis.readings import read_component_latest
from ada.web.ui.stockpile import StockpileValues

from .definitions import STOCKPILE_MINA_KPI_KEYS


def map_stockpile_mina_store(store_data: object) -> tuple[StockpileValues, ...]:
    readings = read_component_latest(store_data)
    return tuple(
        StockpileValues(
            percent=readings.text(percentage_key),
            height_m=readings.text(height_m_key),
        )
        for _, percentage_key, height_m_key in STOCKPILE_MINA_KPI_KEYS
    )
