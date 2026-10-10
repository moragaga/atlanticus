from __future__ import annotations

from ada.web.kpis.readings import (
    read_component_latest,
)
from .definitions import DUCTOS
from .models import StrDuctReading, StrPumpReading


# Preserva estados individuales de ductos y bombas con lecturas por clave.
def map_str_ductos_store(store_data: object) -> tuple[StrDuctReading, ...]:
    source = read_component_latest(store_data)
    return tuple(
        StrDuctReading(
            definition=definition,
            state=source.text(definition.state_kpi_key),
            solids_in=source.text(definition.solids_in_kpi_key),
            solids_out=source.text(definition.solids_out_kpi_key),
            pumps=tuple(
                StrPumpReading(pump, source.text(pump.state_kpi_key))
                for pump in definition.pumps
            ),
        )
        for definition in DUCTOS
    )
