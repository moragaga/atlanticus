from __future__ import annotations

# Contratos inmutables: puntos ordenados en UTC y huecos representados por None.
# La zona horaria de pantalla no se guarda ni modifica el valor temporal.
import math
from dataclasses import dataclass
from datetime import datetime

from ada.web.ui.display_status import DisplayStatus


@dataclass(frozen=True, slots=True)
class TimeSeriesPoint:
    timestamp_utc: datetime
    value: float | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.timestamp_utc, datetime)
            or self.timestamp_utc.tzinfo is None
            or self.timestamp_utc.utcoffset() is None
        ):
            raise ValueError('Time series timestamp must be timezone-aware')
        if self.timestamp_utc.utcoffset().total_seconds() != 0:
            raise ValueError('Time series timestamp must use UTC')
        if self.value is not None and (
            isinstance(self.value, bool)
            or not isinstance(self.value, int | float)
            or not math.isfinite(self.value)
        ):
            raise ValueError('Time series value must be finite numeric or None')


@dataclass(frozen=True, slots=True)
class TimeSeriesValues:
    status: DisplayStatus
    points: tuple[TimeSeriesPoint, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, DisplayStatus):
            raise TypeError('Time series status must be DisplayStatus')
        if not isinstance(self.points, tuple) or not all(
            isinstance(point, TimeSeriesPoint) for point in self.points
        ):
            raise TypeError('Time series points must be a tuple of TimeSeriesPoint')
        if self.status is not DisplayStatus.OK and self.points:
            raise ValueError('Non-OK time series cannot contain points')
        if self.status is DisplayStatus.OK and (
            not self.points or not any(point.value is not None for point in self.points)
        ):
            raise ValueError('OK time series requires at least one numeric point')
        if any(
            left.timestamp_utc >= right.timestamp_utc
            for left, right in zip(self.points, self.points[1:], strict=False)
        ):
            raise ValueError('Time series timestamps must be strictly increasing in UTC')
