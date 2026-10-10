from __future__ import annotations

from collections.abc import Mapping

from ada.web.ui.display_status import DisplayValue

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


# Distribuye las lecturas preparadas según las definiciones de los equipos.
def map_colectiva_process_readings(
    readings: Mapping[str, DisplayValue],
) -> ColectivaProcessReading:
    def state(definition: ColectivaStateDefinition) -> ColectivaStateReading:
        return ColectivaStateReading(
            definition=definition,
            state=readings[definition.state_kpi_key],
        )

    def equipment(definition: ColectivaEquipmentDefinition) -> ColectivaEquipmentReading:
        return ColectivaEquipmentReading(
            definition=definition,
            state=readings[definition.state_kpi_key],
            amperage=(
                readings[definition.amperage_kpi_key]
                if definition.amperage_kpi_key is not None
                else None
            ),
        )

    return ColectivaProcessReading(
        roughers=tuple(map(state, ROUGHERS)),
        vertimills=tuple(map(equipment, VERTIMILLS)),
        bombas=tuple(tuple(map(equipment, group)) for group in BOMBAS),
        columns_operating=readings[COLUMNS_OPERATING_KEY],
        columns_total=readings[COLUMNS_TOTAL_KEY],
        scavengers=tuple(map(state, SCAVENGERS)),
    )
