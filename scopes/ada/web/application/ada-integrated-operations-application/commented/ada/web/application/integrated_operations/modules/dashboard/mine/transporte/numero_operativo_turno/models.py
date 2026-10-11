# Estado interno de N° Operativo • Turno.
from __future__ import annotations

from dataclasses import dataclass

from ada.web.kpis.readings import (
    KpiPayloadDataState,
)


@dataclass(frozen=True, slots=True)
class NumeroOperativoTurnoState:
    # Los valores ya vienen resueltos por backend; Web no suma ni deriva categorías.
    values: tuple[tuple[str, str | int | float | bool], ...]
    data_state: KpiPayloadDataState

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
        if not isinstance(self.data_state, KpiPayloadDataState):
            raise TypeError(
                'Numero Operativo Turno data_state must be KpiPayloadDataState'
            )

    def as_mapping(self) -> dict[str, str | int | float | bool]:
        return dict(self.values)
