from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class KpiHistorianIterationStatus(StrEnum):
    KPI_WATERMARK_MISSING = 'kpi_watermark_missing'
    SKIPPED_CURRENT = 'skipped_current'
    PROCESSED = 'processed'


@dataclass(frozen=True, slots=True)
class KpiHistorianIterationResult:
    status: KpiHistorianIterationStatus
    kpi_committed_watermark_utc: str | None = None
    historian_before_watermark_utc: str | None = None
    historian_after_watermark_utc: str | None = None
    historian_revision: str | None = None
    batches_processed: int = 0
    evaluations_processed: int = 0
    history_rows: int = 0
    error_rows: int = 0
    history_publications: int = 0
    error_publications: int = 0


@dataclass(frozen=True, slots=True)
class KpiHistorianWriteResult:
    batches_processed: int
    evaluations_processed: int
    history_rows: int
    error_rows: int
    history_publications: int
    error_publications: int
    last_watermark_utc: str | None
