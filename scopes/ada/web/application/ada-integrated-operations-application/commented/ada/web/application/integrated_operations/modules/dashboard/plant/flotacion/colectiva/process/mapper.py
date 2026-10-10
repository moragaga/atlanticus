# Normaliza las proyecciones latest y timeseries sin mezclar sus estados.
from __future__ import annotations

from ..mapper import display_value, latest_values
from .definitions import (
    BOMBAS,
    COLUMNS_OPERATING_KEY,
    COLUMNS_TOTAL_KEY,
    ROUGHERS,
    SCAVENGERS,
    VERTIMILLS,
    ColectivaEquipmentDefinition,
    ColectivaStateDefinition,
)
from .models import ColectivaEquipmentReading, ColectivaProcessReading, ColectivaStateReading


# Los equipos comparten lectura pero mantienen identidades y estados propios.
def map_colectiva_process_store(store_data: object) -> ColectivaProcessReading:
    values, status = latest_values(store_data)

    def state(definition: ColectivaStateDefinition) -> ColectivaStateReading:
        return ColectivaStateReading(
            definition=definition,
            state=display_value(values, definition.state_kpi_key, status),
        )

    def equipment(definition: ColectivaEquipmentDefinition) -> ColectivaEquipmentReading:
        return ColectivaEquipmentReading(
            definition=definition,
            state=display_value(values, definition.state_kpi_key, status),
            amperage=(
                display_value(values, definition.amperage_kpi_key, status)
                if definition.amperage_kpi_key is not None
                else None
            ),
        )

    return ColectivaProcessReading(
        roughers=tuple(map(state, ROUGHERS)),
        vertimills=tuple(map(equipment, VERTIMILLS)),
        bombas=tuple(tuple(map(equipment, group)) for group in BOMBAS),
        columns_operating=display_value(values, COLUMNS_OPERATING_KEY, status),
        columns_total=display_value(values, COLUMNS_TOTAL_KEY, status),
        scavengers=tuple(map(state, SCAVENGERS)),
    )
