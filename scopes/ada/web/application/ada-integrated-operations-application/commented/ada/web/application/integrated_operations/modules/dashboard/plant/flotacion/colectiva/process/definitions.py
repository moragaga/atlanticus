# Declara claves y orden de visualización sin depender de datos operacionales.
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ColectivaStateDefinition:
    label: str
    state_kpi_key: str


@dataclass(frozen=True, slots=True)
class ColectivaEquipmentDefinition:
    label: str
    image: str
    state_kpi_key: str
    amperage_kpi_key: str | None = None


ROUGHERS = tuple(
    ColectivaStateDefinition(f'R{number}', f'estado_rougher_{number}')
    for number in range(1, 10)
)
SCAVENGERS = tuple(
    ColectivaStateDefinition(f'SC{number}', f'estado_scavenger_{number}')
    for number in range(1, 3)
)
VERTIMILLS = tuple(
    ColectivaEquipmentDefinition(
        label=f'VT-{number}',
        image='vertimil',
        state_kpi_key=f'estado_vertimil_{number}_inst',
        amperage_kpi_key=f'amperaje_vertimil_{number}_inst',
    )
    for number in ('009', '010', '701')
)
BOMBAS = (
    (
        ColectivaEquipmentDefinition('PP45', 'bomba', 'estado_bomba045_inst'),
        ColectivaEquipmentDefinition('PP46', 'bomba', 'estado_bomba046_inst'),
    ),
    (
        ColectivaEquipmentDefinition('PP52', 'bomba', 'estado_bomba052_inst'),
        ColectivaEquipmentDefinition('PP53', 'bomba', 'estado_bomba053_inst'),
    ),
    (
        ColectivaEquipmentDefinition('PP855', 'bomba', 'estado_bomba855_inst'),
        ColectivaEquipmentDefinition('PP856', 'bomba', 'estado_bomba856_inst'),
    ),
)
COLUMNS_OPERATING_KEY = 'numero_columnas_operando'
COLUMNS_TOTAL_KEY = 'numero_columnas_totales'
