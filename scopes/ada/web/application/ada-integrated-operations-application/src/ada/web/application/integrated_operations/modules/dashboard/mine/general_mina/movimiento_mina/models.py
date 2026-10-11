from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ada.web.kpis.readings import (
    KpiPayloadDataState,
)
from ada.web.ui.display_status import (
    ValueSeverity,
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
    status: ValueSeverity

    def __post_init__(self) -> None:
        if not isinstance(self.status, ValueSeverity):
            raise TypeError('status must be ValueSeverity')


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
    data_state: KpiPayloadDataState

    def __post_init__(self) -> None:
        if not isinstance(self.rows, tuple):
            raise TypeError('rows must be a tuple')
        if self.data_state is not KpiPayloadDataState.ERROR:
            if tuple(row.key for row in self.rows) != MOVIMIENTO_MINA_ROW_KEYS:
                raise ValueError('Movimiento Mina rows must match the canonical row order')
        elif self.rows and tuple(row.key for row in self.rows) != MOVIMIENTO_MINA_ROW_KEYS:
            raise ValueError('Movimiento Mina error rows must match the canonical row order')
        if not isinstance(self.data_state, KpiPayloadDataState):
            raise TypeError('data_state must be KpiPayloadDataState')
