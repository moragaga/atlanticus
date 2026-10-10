from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue

from .definitions import ColectivaEquipmentDefinition, ColectivaStateDefinition


@dataclass(frozen=True, slots=True)
class ColectivaStateReading:
    definition: ColectivaStateDefinition
    state: DisplayValue


@dataclass(frozen=True, slots=True)
class ColectivaEquipmentReading:
    definition: ColectivaEquipmentDefinition
    state: DisplayValue
    amperage: DisplayValue | None = None


@dataclass(frozen=True, slots=True)
class ColectivaProcessReading:
    roughers: tuple[ColectivaStateReading, ...]
    vertimills: tuple[ColectivaEquipmentReading, ...]
    bombas: tuple[tuple[ColectivaEquipmentReading, ...], ...]
    columns_operating: DisplayValue
    columns_total: DisplayValue
    scavengers: tuple[ColectivaStateReading, ...]
