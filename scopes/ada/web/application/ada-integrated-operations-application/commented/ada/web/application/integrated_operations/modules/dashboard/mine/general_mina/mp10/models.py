# MP10 no tiene estado de turno: cada KPI depende directamente de la disponibilidad de su fuente API.
from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import (
    DisplayStatus,
    ValueSeverity,
)


@dataclass(frozen=True, slots=True)
class MP10MetricState:
    # El backend entrega el valor listo para mostrar junto con la alerta y su severidad semántica.
    value: str | int | float | bool
    alert: str | None
    status: ValueSeverity

    def __post_init__(self) -> None:
        if not isinstance(self.value, str | int | float | bool):
            raise TypeError('MP10 value must be a scalar')
        if self.alert is not None and (
            not isinstance(self.alert, str) or not self.alert.strip()
        ):
            raise ValueError('MP10 alert must be null or a non-empty string')
        if not isinstance(self.status, ValueSeverity):
            raise TypeError('MP10 status must be ValueSeverity')


@dataclass(frozen=True, slots=True)
class MP10State:
    # Instantáneo y proyección se degradan por separado porque son KPI independientes.
    instant: MP10MetricState | None
    instant_status: DisplayStatus
    projection: MP10MetricState | None
    projection_status: DisplayStatus

    def __post_init__(self) -> None:
        if not isinstance(self.instant_status, DisplayStatus):
            raise TypeError('MP10 instant_status must be DisplayStatus')
        if not isinstance(self.projection_status, DisplayStatus):
            raise TypeError('MP10 projection_status must be DisplayStatus')
        if self.instant is None and self.instant_status is DisplayStatus.OK:
            raise ValueError('MP10 instant cannot be null when instant_status is OK')
        if self.instant is not None and self.instant_status is not DisplayStatus.OK:
            raise ValueError('MP10 instant_status must be OK when instant is present')
        if self.projection is None and self.projection_status is DisplayStatus.OK:
            raise ValueError('MP10 projection cannot be null when projection_status is OK')
        if self.projection is not None and self.projection_status is not DisplayStatus.OK:
            raise ValueError('MP10 projection_status must be OK when projection is present')
