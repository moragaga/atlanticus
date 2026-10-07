# Modelos internos del contrato JSON de Equipos de Servicio.
from __future__ import annotations

from dataclasses import dataclass

from ada.web.application.integrated_operations.modules.dashboard.data_state import (
    DashboardDataState,
)
from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)


@dataclass(frozen=True, slots=True)
class EquiposServicioComparison:
    # real y plan son valores opacos; Web sólo interpreta status para presentación.
    real: str | int | float | bool
    plan: str | int | float | bool
    status: DashboardValueStatus

    def __post_init__(self) -> None:
        if not isinstance(self.real, str | int | float | bool):
            raise TypeError('Equipos Servicio real must be a scalar')
        if not isinstance(self.plan, str | int | float | bool):
            raise TypeError('Equipos Servicio plan must be a scalar')
        if not isinstance(self.status, DashboardValueStatus):
            raise TypeError('Equipos Servicio status must be DashboardValueStatus')


@dataclass(frozen=True, slots=True)
class EquiposServicioRow:
    # is_total explicita la semántica visual de la fila sin depender del texto de equipo.
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
    # El orden de rows es propiedad de backend y se conserva sin sorting.
    rows: tuple[EquiposServicioRow, ...]
    data_state: DashboardDataState

    def __post_init__(self) -> None:
        if not isinstance(self.rows, tuple):
            raise TypeError('Equipos Servicio rows must be a tuple')
        if not isinstance(self.data_state, DashboardDataState):
            raise TypeError('Equipos Servicio data_state must be DashboardDataState')
