from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StrPumpDefinition:
    label: str
    state_kpi_key: str


@dataclass(frozen=True, slots=True)
class StrDuctDefinition:
    label: str
    state_kpi_key: str
    solids_in_kpi_key: str
    solids_out_kpi_key: str
    pumps: tuple[StrPumpDefinition, ...]


DUCTOS = (
    StrDuctDefinition(
        label='36',
        state_kpi_key='estado_str_36_inst',
        solids_in_kpi_key='solido_entrada_str_36_inst',
        solids_out_kpi_key='solido_salida_str_36_inst',
        pumps=(
            StrPumpDefinition('PP003', 'estado_bomba_003_inst'),
            StrPumpDefinition('PP004', 'estado_bomba_004_inst'),
            StrPumpDefinition('PP1005', 'estado_bomba_1005_inst'),
        ),
    ),
    StrDuctDefinition(
        label='28',
        state_kpi_key='estado_str_28_inst',
        solids_in_kpi_key='solido_entrada_str_28_inst',
        solids_out_kpi_key='solido_salida_str_28_inst',
        pumps=(
            StrPumpDefinition('PP1010', 'estado_bomba_1010_inst'),
            StrPumpDefinition('PP1011', 'estado_bomba_1011_inst'),
        ),
    ),
)
