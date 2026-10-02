# Espejo pedagógico de Latest Delivery multi-Tool: models.py.
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ada.kpis.core import KpiWatermark
from ada.processes.kpi_delivery.errors import KpiDeliveryRepositoryError

_DIGEST = re.compile(r'[0-9a-f]{64}\Z')


# Agrupa una responsabilidad con estado o contrato propio.
class KpiLatestPublicationStatus(StrEnum):
    PUBLISHED = 'published'
    UNCHANGED = 'unchanged'


@dataclass(frozen=True, slots=True)
# Agrupa una responsabilidad con estado o contrato propio.
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


@dataclass(frozen=True, slots=True)
# Agrupa una responsabilidad con estado o contrato propio.
class KpiDeliveryCheckpoint:
    watermark: KpiWatermark
    registry_revision: str
    registry_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.watermark, KpiWatermark):
            raise KpiDeliveryRepositoryError('checkpoint watermark must be KpiWatermark')
        if (
            not isinstance(self.registry_revision, str)
            or not self.registry_revision
            or self.registry_revision != self.registry_revision.strip()
        ):
            raise KpiDeliveryRepositoryError(
                'checkpoint registry_revision must be non-empty trimmed text'
            )
        if not isinstance(self.registry_digest, str) or _DIGEST.fullmatch(
            self.registry_digest
        ) is None:
            raise KpiDeliveryRepositoryError(
                'checkpoint registry_digest must be a sha256 digest'
            )


# Agrupa una responsabilidad con estado o contrato propio.
class KpiLatestDeliveryIterationStatus(StrEnum):
    PUBLISHED = 'published'
    UNCHANGED = 'unchanged'
    SKIPPED_CURRENT = 'skipped_current'
    KPI_WATERMARK_MISSING = 'kpi_watermark_missing'


@dataclass(frozen=True, slots=True)
# Agrupa una responsabilidad con estado o contrato propio.
class KpiLatestDeliveryIterationResult:
    status: KpiLatestDeliveryIterationStatus
    watermark_utc: str | None = None
    tool_count: int = 0
    pending_tool_count: int = 0
    published_tool_count: int = 0
    unchanged_tool_count: int = 0
    failed_tool_count: int = 0
