from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ada.kpis.core import KpiWatermark


class KpiTimeseriesPublicationStatus(StrEnum):
    PUBLISHED = 'published'
    UNCHANGED = 'unchanged'


@dataclass(frozen=True, slots=True)
class KpiTimeseriesPublication:
    status: KpiTimeseriesPublicationStatus
    revision: str


@dataclass(frozen=True, slots=True)
class KpiTimeseriesCheckpoint:
    watermark: KpiWatermark
    configuration_revision: str

    def __post_init__(self) -> None:
        if not isinstance(self.watermark, KpiWatermark):
            raise TypeError('watermark must be KpiWatermark')
        if not isinstance(self.configuration_revision, str) or not self.configuration_revision:
            raise ValueError('configuration_revision must be non-empty')
        if self.configuration_revision != self.configuration_revision.strip():
            raise ValueError('configuration_revision must not contain surrounding whitespace')


class KpiTimeseriesDeliveryIterationStatus(StrEnum):
    PUBLISHED = 'published'
    UNCHANGED = 'unchanged'
    SKIPPED_CURRENT = 'skipped_current'
    HISTORIAN_WATERMARK_MISSING = 'historian_watermark_missing'


@dataclass(frozen=True, slots=True)
class KpiTimeseriesDeliveryIterationResult:
    status: KpiTimeseriesDeliveryIterationStatus
    configuration_revision: str
    watermark_utc: str | None = None
    historian_revision: str | None = None
    delivery_revision: str | None = None
    destination_count: int = 0
    series_count: int = 0
