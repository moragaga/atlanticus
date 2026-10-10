# Contrato compartido de KPI. Mantiene equivalencia funcional con el módulo productivo.
from __future__ import annotations

from ada.kpis.core import KpiStatus, KpiValueKind
from ada.kpis.delivery import KpiDeliveryStatus, KpiLatestValue
from ada.kpis.persistence import KpiEvaluationBatch


def delivery_values_from_batch(batch: KpiEvaluationBatch) -> dict[str, KpiLatestValue]:
    if not isinstance(batch, KpiEvaluationBatch):
        raise TypeError('batch must be KpiEvaluationBatch')
    values: dict[str, KpiLatestValue] = {}
    for evaluation in batch.evaluations:
        if evaluation.status is KpiStatus.MISSING:
            projected = KpiLatestValue(
                status=KpiDeliveryStatus.MISSING,
                value_kind=(
                    evaluation.value_kind.value
                    if evaluation.value_kind is KpiValueKind.JSON
                    else None
                ),
                value=None,
            )
        elif evaluation.status is KpiStatus.ERROR:
            projected = KpiLatestValue(
                status=KpiDeliveryStatus.ERROR,
                value_kind=evaluation.value_kind.value,
                value=None,
                value_type=None if evaluation.value_type is None else evaluation.value_type.value,
            )
        else:
            projected = KpiLatestValue(
                status=KpiDeliveryStatus.OK,
                value_kind=evaluation.value_kind.value,
                value=evaluation.value,
                value_type=(
                    evaluation.value_type.value
                    if evaluation.value_kind is KpiValueKind.VALUE
                    else None
                ),
                parsed_value=(
                    evaluation.parsed_value
                    if evaluation.value_kind is KpiValueKind.VALUE
                    else None
                ),
            )
        values[evaluation.key] = projected
    return values
