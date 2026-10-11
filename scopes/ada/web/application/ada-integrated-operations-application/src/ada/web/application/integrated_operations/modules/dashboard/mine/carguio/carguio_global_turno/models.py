from __future__ import annotations

from dataclasses import dataclass

from ada.web.kpis.readings import (
    KpiPayloadDataState,
)
from ada.web.ui.display_status import (
    ValueSeverity,
)


@dataclass(frozen=True, slots=True)
class CarguioGlobalTurnoComparison:
    real: str | int | float | bool
    plan: str | int | float | bool
    status: ValueSeverity

    def __post_init__(self) -> None:
        if not isinstance(self.real, str | int | float | bool):
            raise TypeError('Carguio Global Turno real must be a scalar')
        if not isinstance(self.plan, str | int | float | bool):
            raise TypeError('Carguio Global Turno plan must be a scalar')
        if not isinstance(self.status, ValueSeverity):
            raise TypeError('Carguio Global Turno status must be ValueSeverity')


@dataclass(frozen=True, slots=True)
class CarguioGlobalTurnoRow:
    flota: str
    is_total: bool
    op_req: CarguioGlobalTurnoComparison
    disponibilidad: CarguioGlobalTurnoComparison
    uebd: CarguioGlobalTurnoComparison
    rendimiento: CarguioGlobalTurnoComparison

    def __post_init__(self) -> None:
        if not isinstance(self.flota, str) or not self.flota.strip():
            raise ValueError('Carguio Global Turno flota must be a non-empty string')
        if not isinstance(self.is_total, bool):
            raise TypeError('Carguio Global Turno is_total must be bool')
        for value in (
            self.op_req,
            self.disponibilidad,
            self.uebd,
            self.rendimiento,
        ):
            if not isinstance(value, CarguioGlobalTurnoComparison):
                raise TypeError('Carguio Global Turno metrics must be comparisons')


@dataclass(frozen=True, slots=True)
class CarguioGlobalTurnoState:
    rows: tuple[CarguioGlobalTurnoRow, ...]
    data_state: KpiPayloadDataState

    def __post_init__(self) -> None:
        if not isinstance(self.rows, tuple):
            raise TypeError('Carguio Global Turno rows must be a tuple')
        if not isinstance(self.data_state, KpiPayloadDataState):
            raise TypeError('Carguio Global Turno data_state must be KpiPayloadDataState')
