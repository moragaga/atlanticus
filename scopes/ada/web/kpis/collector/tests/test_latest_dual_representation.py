from ada.web.kpis.collector.latest import KpiLatestValueState, decode_kpi_latest_value


def test_scalar_and_json_dual_representation_contract():
    value = decode_kpi_latest_value(
        {
            'status': 'ok',
            'value_kind': 'value',
            'value_type': 'float',
            'value': '1234.29',
            'parsed_value': '1.234,29',
        }
    )
    assert value.state is KpiLatestValueState.OK
    assert (value.value, value.parsed_value, value.value_type) == ('1234.29', '1.234,29', 'float')
    structured = decode_kpi_latest_value(
        {
            'status': 'ok',
            'value_kind': 'json',
            'value_type': None,
            'value': {'rows': []},
            'parsed_value': None,
        }
    )
    assert structured.state is KpiLatestValueState.OK
    assert structured.value == {'rows': []}


def test_old_triplet_is_explicitly_rejected():
    assert (
        decode_kpi_latest_value({'status': 'ok', 'value_kind': 'value', 'value': '1.234,29'}).state
        is KpiLatestValueState.INVALID
    )


def test_missing_json_preserves_state():
    result = decode_kpi_latest_value(
        {
            'status': 'missing',
            'value_kind': 'json',
            'value_type': None,
            'value': None,
            'parsed_value': None,
        }
    )
    assert result.state is KpiLatestValueState.MISSING
