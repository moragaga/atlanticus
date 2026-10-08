from __future__ import annotations

from dataclasses import dataclass

from ada.web.application.integrated_operations.modules.dashboard.data_state import (
    DashboardDataState,
)


@dataclass(frozen=True, slots=True)
class NumeroOperativoTurnoState:
    values: tuple[tuple[str, str | int | float | bool], ...]
    data_state: DashboardDataState

    def __post_init__(self) -> None:
        if not isinstance(self.values, tuple):
            raise TypeError('Numero Operativo Turno values must be a tuple')
        for item in self.values:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not isinstance(item[1], str | int | float | bool)
            ):
                raise TypeError(
                    'Numero Operativo Turno values must contain scalar pairs'
                )
        if not isinstance(self.data_state, DashboardDataState):
            raise TypeError(
                'Numero Operativo Turno data_state must be DashboardDataState'
            )

    def as_mapping(self) -> dict[str, str | int | float | bool]:
        return dict(self.values)
