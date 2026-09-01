from __future__ import annotations

# Espejo pedagógico: conserva el comportamiento productivo y documenta la responsabilidad de este módulo.
from dataclasses import dataclass
from enum import StrEnum

from ada.kpis.core import KpiWatermark
from ada.kpis.persistence import KpiEvaluationWriteStatus


class KpiRuntimeOutcome(StrEnum):
    COMPLETED = 'completed'
    EMPTY = 'empty'


@dataclass(frozen=True, slots=True)
class KpiRuntimeIterationResult:
    outcome: KpiRuntimeOutcome
    reason: str
    source_watermark: KpiWatermark | None
    committed_before: KpiWatermark | None
    committed_after: KpiWatermark | None
    evaluation_write_status: KpiEvaluationWriteStatus | None = None
    evaluation_count: int = 0
