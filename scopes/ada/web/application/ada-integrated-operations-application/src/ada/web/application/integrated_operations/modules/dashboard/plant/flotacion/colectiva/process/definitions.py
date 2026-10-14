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
    ColectivaStateDefinition(f'R{number}', f'estado_rougher_{number}') for number in range(1, 10)
)
SCAVENGERS = tuple(
    ColectivaStateDefinition(f'SC{number}', f'estado_scavenger_{number}') for number in range(1, 3)
)
VERTIMILLS = tuple(
    ColectivaEquipmentDefinition(
        label=f'VT-{number}',
        image='vertimil',
        state_kpi_key=f'vertimil_{number}_estado_inst',
        amperage_kpi_key=f'vertimil_{number}_amperaje_inst',
    )
    for number in ('009', '010', '701')
)
BOMBAS = (
    (
        ColectivaEquipmentDefinition('PP45', 'bomba', 'bomba_045_estado_inst'),
        ColectivaEquipmentDefinition('PP46', 'bomba', 'bomba_046_estado_inst'),
    ),
    (
        ColectivaEquipmentDefinition('PP52', 'bomba', 'bomba_052_estado_inst'),
        ColectivaEquipmentDefinition('PP53', 'bomba', 'bomba_053_estado_inst'),
    ),
    (
        ColectivaEquipmentDefinition('PP855', 'bomba', 'bomba_855_estado_inst'),
        ColectivaEquipmentDefinition('PP856', 'bomba', 'bomba_856_estado_inst'),
    ),
)
COLUMNS_OPERATING_KEY = 'numero_columnas_operando'
COLUMNS_TOTAL_KEY = 'numero_columnas_totales'
