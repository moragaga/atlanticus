from datetime import UTC, datetime

from ada.kpis.core import (
    KpiEvaluation,
    KpiResult,
    KpiStatus,
    KpiValueKind,
    KpiValueType,
    KpiWatermark,
)
from ada.kpis.persistence import KpiEvaluationBatch


def watermark(minute: int) -> KpiWatermark:
    return KpiWatermark(datetime(2026, 8, 31, 12, minute, tzinfo=UTC))


def batch(minute: int, value: float = 1.0) -> KpiEvaluationBatch:
    mark = watermark(minute)
    neutral = str(value)
    return KpiEvaluationBatch(
        watermark=mark,
        evaluations=(
            KpiEvaluation(
                key='kpi-a',
                area='general',
                watermark=mark,
                evaluated_at_utc=mark.timestamp_utc,
                result=KpiResult(
                    KpiStatus.OK,
                    KpiValueKind.VALUE,
                    value=neutral,
                    parsed_value=neutral.replace('.', ','),
                    value_type=KpiValueType.FLOAT,
                ),
            ),
        ),
    )
