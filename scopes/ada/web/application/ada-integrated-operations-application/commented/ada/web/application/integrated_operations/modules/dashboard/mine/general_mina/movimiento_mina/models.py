# Modelos internos de Movimiento Mina. Los valores permanecen opacos y sólo se tipan estados estructurales.
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ada.web.application.integrated_operations.modules.dashboard.data_state import (
    DashboardDataState,
)
from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)

MOVIMIENTO_MINA_KPI_KEY = 'movimiento_mina'


class MovimientoMinaRowKey(StrEnum):
    EXTRACCION_MINA = 'extraccion_mina'
    REMANEJO = 'remanejo'
    MOVIMIENTO_MINA = 'movimiento_mina'
    FASE_9 = 'fase_9'
    FASE_10 = 'fase_10'
    FASE_11 = 'fase_11'
    FASE_12 = 'fase_12'


MOVIMIENTO_MINA_ROW_KEYS = tuple(MovimientoMinaRowKey)


@dataclass(frozen=True, slots=True)
class MovimientoMinaComparison:
    value: object
    plan: object
    status: DashboardValueStatus

    def __post_init__(self) -> None:
        if not isinstance(self.status, DashboardValueStatus):
            raise TypeError('status must be DashboardValueStatus')


@dataclass(frozen=True, slots=True)
class MovimientoMinaRow:
    key: MovimientoMinaRowKey
    avance: MovimientoMinaComparison
    cierre: MovimientoMinaComparison
    ritmo: object

    def __post_init__(self) -> None:
        if not isinstance(self.key, MovimientoMinaRowKey):
            raise TypeError('key must be MovimientoMinaRowKey')
        if not isinstance(self.avance, MovimientoMinaComparison):
            raise TypeError('avance must be MovimientoMinaComparison')
        if not isinstance(self.cierre, MovimientoMinaComparison):
            raise TypeError('cierre must be MovimientoMinaComparison')


@dataclass(frozen=True, slots=True)
class MovimientoMinaState:
    rows: tuple[MovimientoMinaRow, ...]
    data_state: DashboardDataState

    def __post_init__(self) -> None:
        if not isinstance(self.rows, tuple):
            raise TypeError('rows must be a tuple')
        # OK y UNSHIFT conservan las siete filas. ERROR puede omitirlas por completo.
        if self.data_state is not DashboardDataState.ERROR:
            if tuple(row.key for row in self.rows) != MOVIMIENTO_MINA_ROW_KEYS:
                raise ValueError('Movimiento Mina rows must match the canonical row order')
        elif self.rows and tuple(row.key for row in self.rows) != MOVIMIENTO_MINA_ROW_KEYS:
            raise ValueError('Movimiento Mina error rows must match the canonical row order')
        if not isinstance(self.data_state, DashboardDataState):
            raise TypeError('data_state must be DashboardDataState')
