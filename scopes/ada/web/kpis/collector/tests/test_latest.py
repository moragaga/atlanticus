from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value


def _value(value='1234.29', parsed='1.234,29', value_type='float'):
    return {
        'status': 'ok',
        'value_kind': 'value',
        'value_type': value_type,
        'value': value,
        'parsed_value': parsed,
    }


def _json(payload):
    return {
        'status': 'ok',
        'value_kind': 'json',
        'value_type': None,
        'value': payload,
        'parsed_value': None,
    }


def test_decoder_returns_neutral_formatted_and_json_payloads():
    scalar = decode_kpi_latest_value(_value())
    structured = decode_kpi_latest_value(_json({'rows': []}))
    assert scalar.state is KpiLatestValueState.OK
    assert (scalar.value, scalar.parsed_value, scalar.value_type) == (
        '1234.29',
        '1.234,29',
        'float',
    )
    assert structured.state is KpiLatestValueState.OK
    assert structured.value == {'rows': []}


def test_decoder_distinguishes_not_mapped_missing_error_and_invalid():
    assert decode_kpi_latest_value(None, present=False).state is KpiLatestValueState.NOT_MAPPED
    assert (
        decode_kpi_latest_value(
            {
                'status': 'missing',
                'value_kind': None,
                'value_type': None,
                'value': None,
                'parsed_value': None,
            }
        ).state
        is KpiLatestValueState.MISSING
    )
    assert (
        decode_kpi_latest_value(
            {
                'status': 'error',
                'value_kind': 'value',
                'value_type': 'float',
                'value': None,
                'parsed_value': None,
            }
        ).state
        is KpiLatestValueState.ERROR
    )
    assert decode_kpi_latest_value(_value(value=None)).state is KpiLatestValueState.INVALID


def test_decoder_rejects_json_payload_on_missing_or_error():
    for status in ('missing', 'error'):
        result = decode_kpi_latest_value(
            {
                'status': status,
                'value_kind': 'json',
                'value_type': None,
                'value': {'rows': []},
                'parsed_value': None,
            }
        )
        assert result.state is KpiLatestValueState.INVALID


def test_decoder_rejects_unknown_kind_invalid_payload_and_v1():
    assert (
        decode_kpi_latest_value(
            {
                'status': 'ok',
                'value_kind': 'integer',
                'value_type': None,
                'value': 1,
                'parsed_value': None,
            }
        ).state
        is KpiLatestValueState.INVALID
    )
    assert decode_kpi_latest_value(_json('not-json-structure')).state is KpiLatestValueState.INVALID
    assert (
        decode_kpi_latest_value({'status': 'ok', 'value_kind': 'value', 'value': '1.234,29'}).state
        is KpiLatestValueState.INVALID
    )
