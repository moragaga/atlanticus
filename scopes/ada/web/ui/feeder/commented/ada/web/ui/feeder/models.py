# El componente recibe valores ya normalizados; no conoce el Collector ni claves concretas.
# Un color degradado se conserva para diagnóstico, pero visualmente será neutro.
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ada.web.ui.display_status import DisplayStatus, DisplayValue


class FeederColor(StrEnum):
    NEUTRAL = 'neutral'
    DANGER = 'danger'
    WARNING = 'warning'


@dataclass(frozen=True, slots=True)
class FeederValues:
    percent: DisplayValue
    color: DisplayValue | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.percent, DisplayValue):
            raise TypeError('Feeder percent must be DisplayValue')
        if self.percent.status is DisplayStatus.OK and (
            type(self.percent.value) is not int or self.percent.value < 0
        ):
            raise ValueError('Feeder percent must be a non-negative integer')
        if self.color is not None:
            if not isinstance(self.color, DisplayValue):
                raise TypeError('Feeder color must be DisplayValue or None')
            if self.color.status is DisplayStatus.OK and not isinstance(
                self.color.value, FeederColor
            ):
                raise TypeError('Feeder color must be FeederColor')
