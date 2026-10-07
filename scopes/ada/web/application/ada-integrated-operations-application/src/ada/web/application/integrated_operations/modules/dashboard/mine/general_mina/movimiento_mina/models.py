from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

MOVIMIENTO_MINA_KPI_KEY = 'movimiento_mina'


class MovimientoMinaMetricStatus(StrEnum):
    NEUTRAL = 'neutral'
    DANGER = 'danger'
    WARNING = 'warning'


class MovimientoMinaDataState(StrEnum):
    READY = 'ready'
    UNSHIFT = 'unshift'
    ERROR = 'error'


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
    status: MovimientoMinaMetricStatus

    def __post_init__(self) -> None:
        if not isinstance(self.status, MovimientoMinaMetricStatus):
            raise TypeError('status must be MovimientoMinaMetricStatus')


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
    data_state: MovimientoMinaDataState = MovimientoMinaDataState.READY

    def __post_init__(self) -> None:
        if not isinstance(self.rows, tuple):
            raise TypeError('rows must be a tuple')
        if tuple(row.key for row in self.rows) != MOVIMIENTO_MINA_ROW_KEYS:
            raise ValueError('Movimiento Mina rows must match the canonical row order')
        if not isinstance(self.data_state, MovimientoMinaDataState):
            raise TypeError('data_state must be MovimientoMinaDataState')
