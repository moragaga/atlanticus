from __future__ import annotations

from ..mapper import display_value, history_values, latest_values
from .definitions import COLECTIVA_INDICATORS, COLECTIVA_TREND
from .models import ColectivaIndicatorReading, ColectivaOverviewReading


def map_colectiva_overview_store(store_data: object) -> ColectivaOverviewReading:
    values, status = latest_values(store_data)
    return ColectivaOverviewReading(
        trend_current=display_value(values, COLECTIVA_TREND.kpi_key, status),
        trend_history=history_values(store_data, COLECTIVA_TREND.kpi_key),
        indicators=tuple(
            ColectivaIndicatorReading(definition, display_value(values, definition.kpi_key, status))
            for definition in COLECTIVA_INDICATORS
        ),
    )
