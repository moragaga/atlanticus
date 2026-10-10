# Versión pedagógica: Las asociaciones entre ductos, bombas y sus KPI permanecen sin cambios.
from __future__ import annotations

from collections.abc import Mapping

from ada.web.ui.display_status import DisplayValue

from .definitions import DUCTOS
from .models import StrDuctReading, StrPumpReading


def map_str_ductos_readings(readings: Mapping[str, DisplayValue]) -> tuple[StrDuctReading, ...]:
    return tuple(
        StrDuctReading(
            definition=definition,
            state=readings[definition.state_kpi_key],
            solids_in=readings[definition.solids_in_kpi_key],
            solids_out=readings[definition.solids_out_kpi_key],
            pumps=tuple(
                StrPumpReading(pump, readings[pump.state_kpi_key]) for pump in definition.pumps
            ),
        )
        for definition in DUCTOS
    )
