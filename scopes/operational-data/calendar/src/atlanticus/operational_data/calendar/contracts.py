from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from atlanticus.operational_data.calendar.models import OperationalWeekPartition


@runtime_checkable
class OperationalCalendarResolver(Protocol):
    @property
    def key(self) -> str: ...

    def resolve(self, timestamp_utc: datetime) -> OperationalWeekPartition: ...
