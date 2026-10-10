from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MoliendaSagMetricDefinition:
    label: str
    kpi_key: str
    unit: str | None = None
    color_kpi_key: str | None = None


@dataclass(frozen=True, slots=True)
class MoliendaEquipmentDefinition:
    label: str
    image: str
    state_kpi_key: str
    power_kpi_key: str
    power_color_kpi_key: str | None = None


@dataclass(frozen=True, slots=True)
class MoliendaLineDefinition:
    number: int
    sag: MoliendaEquipmentDefinition
    mills: tuple[MoliendaEquipmentDefinition, ...]
    metrics: tuple[MoliendaSagMetricDefinition, ...]


def _line(number: int, mill_numbers: tuple[int, ...]) -> MoliendaLineDefinition:
    return MoliendaLineDefinition(
        number=number,
        sag=MoliendaEquipmentDefinition(
            label=f'SAG {number}',
            image='sag',
            state_kpi_key=f'estado_sag_{number}_inst',
            power_kpi_key=f'potencia_sag_{number}_inst',
            power_color_kpi_key=f'estado_sag_{number}_color_inst',
        ),
        mills=tuple(
            MoliendaEquipmentDefinition(
                label=f'MB-{mill_number:03d}',
                image='molino_bolas',
                state_kpi_key=f'estado_mb{mill_number:03d}_sag_{number}_inst',
                power_kpi_key=f'potencia_mb{mill_number:03d}_sag_{number}_inst',
                power_color_kpi_key=f'potencia_mb{mill_number:03d}_sag_{number}_color_inst',
            )
            for mill_number in mill_numbers
        ),
        metrics=(
            MoliendaSagMetricDefinition(
                'F80', f'f80_sag_{number}_inst', '"', f'f80_sag_{number}_color_inst'
            ),
            MoliendaSagMetricDefinition(
                'P80', f'p80_sag_{number}_inst', 'µm', f'p80_sag_{number}_color_inst'
            ),
            MoliendaSagMetricDefinition(
                'Rend.', f'tph_sag_{number}_inst', 't/h', f'tph_sag_{number}_color_inst'
            ),
        ),
    )


MOLIENDA_LINES = (
    _line(1, (4, 5)),
    _line(2, (6, 7)),
    _line(3, (8, 9)),
    _line(4, (10,)),
)
