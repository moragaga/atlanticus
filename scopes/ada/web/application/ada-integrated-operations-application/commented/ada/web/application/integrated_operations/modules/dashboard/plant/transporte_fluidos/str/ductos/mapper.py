from __future__ import annotations

# Versión pedagógica: conserva literalmente la lógica y contratos del módulo productivo.


from .._latest import display_value, latest_values
from .definitions import DUCTOS
from .models import StrDuctReading, StrPumpReading


# Cada ducto conserva por separado su estado, sólidos de entrada y salida, y bombas.
def map_str_ductos_store(store_data: object) -> tuple[StrDuctReading, ...]:
    values, status = latest_values(store_data)
    return tuple(
        StrDuctReading(
            definition=definition,
            state=display_value(values, definition.state_kpi_key, status),
            solids_in=display_value(values, definition.solids_in_kpi_key, status),
            solids_out=display_value(values, definition.solids_out_kpi_key, status),
            pumps=tuple(
                StrPumpReading(pump, display_value(values, pump.state_kpi_key, status))
                for pump in definition.pumps
            ),
        )
        for definition in DUCTOS
    )
