from __future__ import annotations

from dataclasses import dataclass

from ada.web.kpis.readings import (
    KpiPayloadDataState,
)
from ada.web.ui.display_status import (
    DisplayStatus,
    DisplayValue,
    ValueSeverity,
)


@dataclass(frozen=True, slots=True)
class RemanentesSummaryRow:
    fase: object
    mineral: object
    esteril: object
    baja_ley: object
    total: object


@dataclass(frozen=True, slots=True)
class RemanentesSummaryState:
    rows: tuple[RemanentesSummaryRow, ...]
    data_state: KpiPayloadDataState

    def __post_init__(self) -> None:
        if not isinstance(self.rows, tuple):
            raise TypeError('Remanentes summary rows must be a tuple')
        if not isinstance(self.data_state, KpiPayloadDataState):
            raise TypeError('Remanentes summary data_state must be KpiPayloadDataState')


@dataclass(frozen=True, slots=True)
class Stock3080State:
    value: DisplayValue
    status: ValueSeverity = ValueSeverity.NEUTRAL

    def __post_init__(self) -> None:
        if not isinstance(self.value, DisplayValue):
            raise TypeError('Stock 3080 value must be DisplayValue')
        if not isinstance(self.status, ValueSeverity):
            raise TypeError('Stock 3080 status must be ValueSeverity')


@dataclass(frozen=True, slots=True)
class RemanentesState:
    summary: RemanentesSummaryState | None
    summary_status: DisplayStatus
    stock_3080: Stock3080State

    def __post_init__(self) -> None:
        if not isinstance(self.summary_status, DisplayStatus):
            raise TypeError('Remanentes summary_status must be DisplayStatus')
        if not isinstance(self.stock_3080, Stock3080State):
            raise TypeError('stock_3080 must be Stock3080State')
        if self.summary is None and self.summary_status is DisplayStatus.OK:
            raise ValueError('Remanentes summary cannot be null when summary_status is OK')
        if self.summary is not None and self.summary_status is not DisplayStatus.OK:
            raise ValueError('Remanentes summary_status must be OK when summary is present')
