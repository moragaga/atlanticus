from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value


def test_decoder_returns_value_and_json_payloads_without_presentation_objects() -> None:
    scalar = decode_kpi_latest_value({'status': 'ok', 'value_kind': 'value', 'value': 42.0})
    structured = decode_kpi_latest_value(
        {'status': 'ok', 'value_kind': 'json', 'value': {'rows': []}}
    )

    assert scalar.state is KpiLatestValueState.OK
    assert scalar.value == 42.0
    assert structured.state is KpiLatestValueState.OK
    assert structured.value == {'rows': []}


def test_decoder_distinguishes_not_mapped_missing_error_and_invalid() -> None:
    assert decode_kpi_latest_value(None, present=False).state is KpiLatestValueState.NOT_MAPPED
    assert (
        decode_kpi_latest_value({'status': 'missing', 'value_kind': None, 'value': None}).state
        is KpiLatestValueState.MISSING
    )
    assert (
        decode_kpi_latest_value({'status': 'error', 'value_kind': 'value', 'value': None}).state
        is KpiLatestValueState.ERROR
    )
    assert (
        decode_kpi_latest_value({'status': 'ok', 'value_kind': 'value', 'value': None}).state
        is KpiLatestValueState.INVALID
    )


def test_decoder_rejects_json_payload_on_missing_or_error() -> None:
    payload = {'rows': []}

    missing = decode_kpi_latest_value({'status': 'missing', 'value_kind': 'json', 'value': payload})
    error = decode_kpi_latest_value({'status': 'error', 'value_kind': 'json', 'value': payload})

    assert missing.state is KpiLatestValueState.INVALID
    assert error.state is KpiLatestValueState.INVALID


def test_decoder_rejects_unknown_value_kind_and_non_structural_json() -> None:
    unknown = decode_kpi_latest_value({'status': 'ok', 'value_kind': 'integer', 'value': 1})
    malformed_json = decode_kpi_latest_value(
        {'status': 'ok', 'value_kind': 'json', 'value': 'not-json-structure'}
    )

    assert unknown.state is KpiLatestValueState.INVALID
    assert malformed_json.state is KpiLatestValueState.INVALID
