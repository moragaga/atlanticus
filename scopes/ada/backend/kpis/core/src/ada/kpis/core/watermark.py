from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Self

from atlanticus.operational_data.core import normalize_utc_second


@dataclass(frozen=True, slots=True, order=True)
class KpiWatermark:
    timestamp_utc: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'timestamp_utc',
            normalize_utc_second(self.timestamp_utc, field_name='KPI watermark'),
        )

    def to_text(self) -> str:
        return self.timestamp_utc.isoformat(timespec='seconds').replace('+00:00', 'Z')

    @classmethod
    def from_text(cls, value: str) -> Self:
        if not isinstance(value, str) or not value:
            raise ValueError('KPI watermark must be a non-empty string')
        try:
            timestamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError as error:
            raise ValueError('KPI watermark is invalid') from error
        return cls(timestamp)
