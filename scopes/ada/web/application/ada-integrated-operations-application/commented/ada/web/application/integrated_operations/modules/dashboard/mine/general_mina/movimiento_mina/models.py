from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# La key identifica la entrada JSON dentro de latest.values del Store de General Mina.
MOVIMIENTO_MINA_KPI_KEY = 'movimiento_mina'


# El modelo interno usa semántica visual, no colores físicos ni códigos CSS.
class MovimientoMinaMetricStatus(StrEnum):
    NEUTRAL = 'neutral'
    DANGER = 'danger'
    WARNING = 'warning'


# READY representa ausencia de aviso; UNSHIFT y ERROR agregan una señal bajo las filas.
class MovimientoMinaDataState(StrEnum):
    READY = 'ready'
    UNSHIFT = 'unshift'
    ERROR = 'error'


# Las siete filas forman parte del contrato actual. Su orden no depende del orden recibido en JSON.
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
    # value y plan son deliberadamente opacos: la Web los conserva sin casting.
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
    # Ritmo no tiene status ni color por contrato.
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
        # La presentación puede confiar en una secuencia completa, estable y canónica.
        if tuple(row.key for row in self.rows) != MOVIMIENTO_MINA_ROW_KEYS:
            raise ValueError('Movimiento Mina rows must match the canonical row order')
        if not isinstance(self.data_state, MovimientoMinaDataState):
            raise TypeError('data_state must be MovimientoMinaDataState')
