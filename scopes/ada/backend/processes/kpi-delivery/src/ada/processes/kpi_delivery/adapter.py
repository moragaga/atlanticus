from __future__ import annotations

from ada.kpis.core import KpiStatus
from ada.kpis.delivery import KpiDeliveryStatus, KpiLatestValue
from ada.kpis.persistence import KpiEvaluationBatch


def delivery_values_from_batch(batch: KpiEvaluationBatch) -> dict[str, KpiLatestValue]:
    if not isinstance(batch, KpiEvaluationBatch):
        raise TypeError('batch must be KpiEvaluationBatch')
    values: dict[str, KpiLatestValue] = {}
    for evaluation in batch.evaluations:
        if evaluation.status is KpiStatus.MISSING:
            projected = KpiLatestValue.missing()
        elif evaluation.status is KpiStatus.ERROR:
            projected = KpiLatestValue(
                status=KpiDeliveryStatus.ERROR,
                value_kind=evaluation.value_kind.value,
                value=None,
            )
        else:
            projected = KpiLatestValue(
                status=KpiDeliveryStatus.OK,
                value_kind=evaluation.value_kind.value,
                value=evaluation.value,
            )
        values[evaluation.key] = projected
    return values
