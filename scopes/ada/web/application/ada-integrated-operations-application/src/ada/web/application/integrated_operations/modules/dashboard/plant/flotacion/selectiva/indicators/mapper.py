from __future__ import annotations

from collections.abc import Mapping

from ada.web.ui.display_status import DisplayValue

from .definitions import SELECTIVA_INDICATORS
from .models import SelectivaIndicatorReading


def map_selectiva_indicators_readings(
    readings: Mapping[str, DisplayValue],
) -> tuple[SelectivaIndicatorReading, ...]:
    return tuple(
        SelectivaIndicatorReading(definition, readings[definition.kpi_key])
        for definition in SELECTIVA_INDICATORS
    )
