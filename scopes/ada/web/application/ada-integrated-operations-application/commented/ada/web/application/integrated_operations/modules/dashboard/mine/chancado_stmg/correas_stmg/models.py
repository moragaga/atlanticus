# El estado local conserva las lecturas independientes y su información de degradación.
from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue


@dataclass(frozen=True, slots=True)
class CorreasStmgState:
    states: tuple[DisplayValue, ...]
    metric: DisplayValue
    metric_color: DisplayValue | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.states, tuple) or not all(
            isinstance(item, DisplayValue) for item in self.states
        ):
            raise TypeError('Correa STMG states must be a tuple of DisplayValue')
        if not isinstance(self.metric, DisplayValue):
            raise TypeError('Correa STMG metric must be DisplayValue')
        if self.metric_color is not None and not isinstance(self.metric_color, DisplayValue):
            raise TypeError('Correa STMG metric_color must be DisplayValue or None')
