from __future__ import annotations

from dataclasses import dataclass

from ada.web.kpis.readings import (
    KpiPayloadDataState,
)
from ada.web.ui.display_status import (
    ValueSeverity,
)


@dataclass(frozen=True, slots=True)
class TransporteGlobalTurnoValue:
    value: str | int | float | bool
    status: ValueSeverity

    def __post_init__(self) -> None:
        if not isinstance(self.value, str | int | float | bool):
            raise TypeError('Transporte Global Turno value must be a scalar')
        if not isinstance(self.status, ValueSeverity):
            raise TypeError('Transporte Global Turno status must be ValueSeverity')


@dataclass(frozen=True, slots=True)
class TransporteGlobalTurnoRow:
    key: str
    real: TransporteGlobalTurnoValue
    plan: TransporteGlobalTurnoValue

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError('Transporte Global Turno key must be non-empty')
        if not isinstance(self.real, TransporteGlobalTurnoValue):
            raise TypeError('Transporte Global Turno real must be a value')
        if not isinstance(self.plan, TransporteGlobalTurnoValue):
            raise TypeError('Transporte Global Turno plan must be a value')


@dataclass(frozen=True, slots=True)
class TransporteGlobalTurnoState:
    rows: tuple[TransporteGlobalTurnoRow, ...]
    data_state: KpiPayloadDataState

    def __post_init__(self) -> None:
        if not isinstance(self.rows, tuple):
            raise TypeError('Transporte Global Turno rows must be a tuple')
        if not isinstance(self.data_state, KpiPayloadDataState):
            raise TypeError('Transporte Global Turno data_state must be KpiPayloadDataState')
