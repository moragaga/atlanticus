import pytest

from ada.kpis.delivery import KpiDeliveryStatus, KpiLatestValue


def test_scalar_payload_transports_both_strings_and_semantic_type():
    value = KpiLatestValue(
        KpiDeliveryStatus.OK,
        'value',
        '1234.29',
        value_type='float',
        parsed_value='1.234,29',
    )
    assert value.to_payload() == {
        'status': 'ok',
        'value_kind': 'value',
        'value_type': 'float',
        'value': '1234.29',
        'parsed_value': '1.234,29',
    }


def test_json_has_original_payload_only():
    value = KpiLatestValue(KpiDeliveryStatus.OK, 'json', {'rows': []})
    assert value.to_payload()['parsed_value'] is None
    assert value.to_payload()['value_type'] is None


def test_scalar_without_parsed_value_is_rejected():
    with pytest.raises(TypeError):
        KpiLatestValue(KpiDeliveryStatus.OK, 'value', '1234.29', value_type='float')
