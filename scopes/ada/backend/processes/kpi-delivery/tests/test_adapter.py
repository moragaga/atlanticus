from __future__ import annotations

from ada.kpis.core import KpiStatus, KpiValueKind, KpiValueType
from ada.kpis.delivery import KpiDeliveryStatus
from ada.processes.kpi_delivery.adapter import delivery_values_from_batch
from tests.support import batch, evaluation


def test_adapter_uses_parsed_value_for_scalar_and_value_for_json() -> None:
    source = batch(
        evaluation(
            'scalar',
            value='1234.29',
            parsed_value='1.234,29',
            value_type=KpiValueType.FLOAT,
        ),
        evaluation(
            'json',
            value_kind=KpiValueKind.JSON,
            value={'value': 1},
        ),
        evaluation('missing', status=KpiStatus.MISSING),
        evaluation('error', status=KpiStatus.ERROR, value_kind=KpiValueKind.JSON),
    )
    values = delivery_values_from_batch(source)
    assert values['scalar'].status is KpiDeliveryStatus.OK
    assert values['scalar'].value_kind == 'value'
    assert values['scalar'].value == '1.234,29'
    assert values['json'].value_kind == 'json'
    assert values['json'].value == {'value': 1}
    assert values['missing'].status is KpiDeliveryStatus.MISSING
    assert values['missing'].value_kind is None
    assert values['missing'].value is None
    assert values['error'].status is KpiDeliveryStatus.ERROR
    assert values['error'].value_kind == 'json'
    assert values['error'].value is None
