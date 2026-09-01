# Define checkpoint, publicación y resultado de iteración.
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ada.kpis.core import KpiWatermark
from ada.processes.kpi_delivery.errors import KpiDeliveryRepositoryError


# Mantiene aislada la responsabilidad de KpiLatestPublicationStatus.
class KpiLatestPublicationStatus(StrEnum):
    PUBLISHED = 'published'
    UNCHANGED = 'unchanged'


# Mantiene aislada la responsabilidad de KpiLatestPublication.
@dataclass(frozen=True, slots=True)
class KpiLatestPublication:
    status: KpiLatestPublicationStatus
    revision: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, KpiLatestPublicationStatus):
            raise TypeError('status must be KpiLatestPublicationStatus')
        if not isinstance(self.revision, str) or not self.revision:
            raise KpiDeliveryRepositoryError('publication revision must be a non-empty string')
        if self.revision != self.revision.strip():
            raise KpiDeliveryRepositoryError(
                'publication revision must not contain surrounding whitespace'
            )

    @property
    def published(self) -> bool:
        return self.status is KpiLatestPublicationStatus.PUBLISHED


# Mantiene aislada la responsabilidad de KpiDeliveryCheckpoint.
@dataclass(frozen=True, slots=True)
class KpiDeliveryCheckpoint:
    watermark: KpiWatermark
    configuration_revision: str

    def __post_init__(self) -> None:
        if not isinstance(self.watermark, KpiWatermark):
            raise KpiDeliveryRepositoryError('checkpoint watermark must be KpiWatermark')
        if not isinstance(self.configuration_revision, str) or not self.configuration_revision:
            raise KpiDeliveryRepositoryError(
                'checkpoint configuration_revision must be a non-empty string'
            )
        if self.configuration_revision != self.configuration_revision.strip():
            raise KpiDeliveryRepositoryError(
                'checkpoint configuration_revision must not contain surrounding whitespace'
            )


# Mantiene aislada la responsabilidad de KpiLatestDeliveryIterationStatus.
class KpiLatestDeliveryIterationStatus(StrEnum):
    PUBLISHED = 'published'
    UNCHANGED = 'unchanged'
    SKIPPED_CURRENT = 'skipped_current'
    KPI_WATERMARK_MISSING = 'kpi_watermark_missing'


# Mantiene aislada la responsabilidad de KpiLatestDeliveryIterationResult.
@dataclass(frozen=True, slots=True)
class KpiLatestDeliveryIterationResult:
    status: KpiLatestDeliveryIterationStatus
    configuration_revision: str
    watermark_utc: str | None = None
    delivery_revision: str | None = None
    destination_count: int = 0
    value_count: int = 0
    missing_count: int = 0
    error_count: int = 0
