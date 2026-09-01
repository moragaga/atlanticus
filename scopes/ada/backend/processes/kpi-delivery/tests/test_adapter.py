from __future__ import annotations

from ada.kpis.core import KpiStatus, KpiValueKind
from ada.kpis.delivery import KpiDeliveryStatus
from ada.processes.kpi_delivery.adapter import delivery_values_from_batch
from tests.support import batch, evaluation


def test_adapter_maps_ok_missing_and_error_without_internal_fields() -> None:
    source = batch(
        evaluation('ok', value='66,00'),
        evaluation('missing', status=KpiStatus.MISSING),
        evaluation('error', status=KpiStatus.ERROR, value_kind=KpiValueKind.JSON),
    )

    values = delivery_values_from_batch(source)

    assert values['ok'].status is KpiDeliveryStatus.OK
    assert values['ok'].value_kind == 'value'
    assert values['ok'].value == '66,00'
    assert values['missing'].status is KpiDeliveryStatus.MISSING
    assert values['missing'].value_kind is None
    assert values['missing'].value is None
    assert values['error'].status is KpiDeliveryStatus.ERROR
    assert values['error'].value_kind == 'json'
    assert values['error'].value is None
