from datetime import UTC, datetime

from ada.kpis.core import KpiEvaluation, KpiResult, KpiStatus, KpiValueKind, KpiWatermark
from ada.kpis.delivery import KpiDeliveryStatus
from ada.kpis.persistence import KpiEvaluationBatch
from ada.processes.kpi_delivery.adapter import delivery_values_from_batch


def test_adapter_preserves_degraded_json_structure() -> None:
    watermark = KpiWatermark(datetime(2026, 9, 1, 5, 0, tzinfo=UTC))
    evaluations = []
    for key, status, error in (
        ('missing-json', KpiStatus.MISSING, None),
        ('error-json', KpiStatus.ERROR, 'RuntimeError'),
    ):
        evaluations.append(
            KpiEvaluation(
                key=key,
                area='general',
                watermark=watermark,
                evaluated_at_utc=watermark.timestamp_utc,
                result=KpiResult(
                    status=status,
                    value_kind=KpiValueKind.JSON,
                    value={'rows': []},
                    error=error,
                ),
            )
        )
    values = delivery_values_from_batch(
        KpiEvaluationBatch(watermark=watermark, evaluations=tuple(evaluations))
    )
    assert values['missing-json'].status is KpiDeliveryStatus.MISSING
    assert values['missing-json'].value_kind == 'json'
    assert values['missing-json'].value == {'rows': []}
    assert values['error-json'].status is KpiDeliveryStatus.ERROR
    assert values['error-json'].value_kind == 'json'
    assert values['error-json'].value == {'rows': []}
