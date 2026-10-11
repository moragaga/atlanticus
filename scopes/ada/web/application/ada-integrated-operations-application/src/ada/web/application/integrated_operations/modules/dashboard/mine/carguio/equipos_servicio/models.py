from __future__ import annotations

from dataclasses import dataclass

from ada.web.kpis.readings import (
    KpiPayloadDataState,
)
from ada.web.ui.display_status import (
    ValueSeverity,
)


@dataclass(frozen=True, slots=True)
class EquiposServicioComparison:
    real: str | int | float | bool
    plan: str | int | float | bool
    status: ValueSeverity

    def __post_init__(self) -> None:
        if not isinstance(self.real, str | int | float | bool):
            raise TypeError('Equipos Servicio real must be a scalar')
        if not isinstance(self.plan, str | int | float | bool):
            raise TypeError('Equipos Servicio plan must be a scalar')
        if not isinstance(self.status, ValueSeverity):
            raise TypeError('Equipos Servicio status must be ValueSeverity')


@dataclass(frozen=True, slots=True)
class EquiposServicioRow:
    equipo: str
    is_total: bool
    operando: EquiposServicioComparison
    disponibles: EquiposServicioComparison
    fuera_servicio: EquiposServicioComparison

    def __post_init__(self) -> None:
        if not isinstance(self.equipo, str) or not self.equipo.strip():
            raise ValueError('Equipos Servicio equipo must be a non-empty string')
        if not isinstance(self.is_total, bool):
            raise TypeError('Equipos Servicio is_total must be bool')
        for value in (
            self.operando,
            self.disponibles,
            self.fuera_servicio,
        ):
            if not isinstance(value, EquiposServicioComparison):
                raise TypeError('Equipos Servicio metrics must be comparisons')


@dataclass(frozen=True, slots=True)
class EquiposServicioState:
    rows: tuple[EquiposServicioRow, ...]
    data_state: KpiPayloadDataState

    def __post_init__(self) -> None:
        if not isinstance(self.rows, tuple):
            raise TypeError('Equipos Servicio rows must be a tuple')
        if not isinstance(self.data_state, KpiPayloadDataState):
            raise TypeError('Equipos Servicio data_state must be KpiPayloadDataState')
