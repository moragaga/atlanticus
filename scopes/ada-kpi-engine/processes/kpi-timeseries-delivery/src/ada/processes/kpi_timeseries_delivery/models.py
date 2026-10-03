from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ada.kpis.core import KpiWatermark
from ada.processes.kpi_timeseries_delivery.errors import (
    KpiTimeseriesDeliveryRepositoryError,
)

_DIGEST = re.compile(r'[0-9a-f]{64}\Z')


class KpiTimeseriesPublicationStatus(StrEnum):
    PUBLISHED = 'published'
    UNCHANGED = 'unchanged'


@dataclass(frozen=True, slots=True)
class KpiTimeseriesPublication:
    status: KpiTimeseriesPublicationStatus
    revision: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, KpiTimeseriesPublicationStatus):
            raise TypeError('status must be KpiTimeseriesPublicationStatus')
        if not isinstance(self.revision, str) or not self.revision:
            raise KpiTimeseriesDeliveryRepositoryError(
                'publication revision must be a non-empty string'
            )
        if self.revision != self.revision.strip():
            raise KpiTimeseriesDeliveryRepositoryError(
                'publication revision must not contain surrounding whitespace'
            )


@dataclass(frozen=True, slots=True)
class KpiTimeseriesCheckpoint:
    watermark: KpiWatermark
    registry_revision: str
    registry_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.watermark, KpiWatermark):
            raise KpiTimeseriesDeliveryRepositoryError('checkpoint watermark must be KpiWatermark')
        if (
            not isinstance(self.registry_revision, str)
            or not self.registry_revision
            or self.registry_revision != self.registry_revision.strip()
        ):
            raise KpiTimeseriesDeliveryRepositoryError(
                'checkpoint registry_revision must be non-empty trimmed text'
            )
        if (
            not isinstance(self.registry_digest, str)
            or _DIGEST.fullmatch(self.registry_digest) is None
        ):
            raise KpiTimeseriesDeliveryRepositoryError(
                'checkpoint registry_digest must be a sha256 digest'
            )


class KpiTimeseriesDeliveryIterationStatus(StrEnum):
    MATERIALIZATION_PENDING = 'materialization_pending'
    PUBLISHED = 'published'
    UNCHANGED = 'unchanged'
    SKIPPED_CURRENT = 'skipped_current'
    HISTORIAN_WATERMARK_MISSING = 'historian_watermark_missing'


@dataclass(frozen=True, slots=True)
class KpiTimeseriesDeliveryIterationResult:
    status: KpiTimeseriesDeliveryIterationStatus
    watermark_utc: str | None = None
    historian_revision: str | None = None
    tool_count: int = 0
    pending_tool_count: int = 0
    published_tool_count: int = 0
    unchanged_tool_count: int = 0
    failed_tool_count: int = 0
