from __future__ import annotations

import pytest

from ada.web.application.integrated_operations.modules.dashboard.kpi_readings import (
    DashboardLatestReadings,
    read_component_latest,
    read_system_latest,
)
from ada.web.ui.display_status import DisplayStatus


def _entry(value: object, *, kind: str = 'value') -> dict[str, object]:
    return {'status': 'ok', 'value_kind': kind, 'value': value}


def _store(values: dict[str, object]) -> dict[str, object]:
    return {'latest': {'values': values}, 'timeseries': {'unrelated': True}}


@pytest.mark.parametrize(
    ('store', 'status'),
    [
        (None, DisplayStatus.INVALID),
        ([], DisplayStatus.INVALID),
        ({}, DisplayStatus.NOT_MAPPED),
        ({'latest': None}, DisplayStatus.NOT_MAPPED),
        ({'latest': []}, DisplayStatus.INVALID),
        ({'latest': {}}, DisplayStatus.INVALID),
        ({'latest': {'values': None}}, DisplayStatus.INVALID),
        ({'latest': {'values': []}}, DisplayStatus.INVALID),
        ({'latest': {'values': {}}}, DisplayStatus.OK),
    ],
)
def test_component_source_status_matches_current_dashboard_mapping(store, status):
    readings = read_component_latest(store)
    assert readings.source_status is status
    assert readings.text('missing').status is (
        DisplayStatus.NOT_MAPPED if status is DisplayStatus.OK else status
    )


def test_latest_uses_values_not_timeseries():
    readings = read_component_latest(_store({'value': _entry(0)}))
    assert readings.text('value').value == '0'
    assert readings.scalar('value').value == 0
    assert readings.source_status is DisplayStatus.OK


def test_missing_error_and_invalid_entries_are_independent():
    readings = read_component_latest(
        _store(
            {
                'ok': _entry(12.5),
                'missing': {'status': 'missing', 'value_kind': None, 'value': None},
                'error': {'status': 'error', 'value_kind': None, 'value': None},
                'malformed': {'status': 'ok', 'value_kind': 'value'},
                'explicit_none': None,
            }
        )
    )
    assert readings.text('ok').status is DisplayStatus.OK
    assert readings.text('absent').status is DisplayStatus.NOT_MAPPED
    assert readings.text('missing').status is DisplayStatus.EMPTY
    assert readings.text('error').status is DisplayStatus.ERROR
    assert readings.text('malformed').status is DisplayStatus.INVALID
    assert readings.text('explicit_none').status is DisplayStatus.INVALID


def test_text_matches_legacy_scalar_policy_without_loss_of_zero():
    readings = read_component_latest(
        _store(
            {
                'string': _entry('  running  '),
                'blank': _entry('   '),
                'integer': _entry(10),
                'float': _entry(2.5),
                'zero': _entry(0),
                'boolean': _entry(False),
            }
        )
    )
    assert readings.text('string').value == 'running'
    assert readings.text('blank').status is DisplayStatus.INVALID
    assert readings.text('integer').value == '10'
    assert readings.text('float').value == '2.5'
    assert readings.text('zero').value == '0'
    assert readings.text('boolean').status is DisplayStatus.INVALID


def test_typed_scalars_support_global_indicator_policy_explicitly():
    readings = read_component_latest(
        _store({'boolean': _entry(False), 'empty_text': _entry(''), 'number': _entry(11)})
    )
    assert readings.scalar('boolean').status is DisplayStatus.INVALID
    assert readings.scalar('boolean', allow_bool=True).value is False
    assert readings.scalar('empty_text').value == ''
    assert readings.scalar('number').value == 11
    assert readings.text('empty_text').status is DisplayStatus.INVALID


def test_json_is_not_coerced_to_text_or_scalar():
    payload = {'rows': [{'value': 1}]}
    readings = read_component_latest(
        _store({'object': _entry(payload, kind='json'), 'list': _entry([1], kind='json')})
    )
    assert readings.json('object').value == payload
    assert readings.json('list').value == [1]
    assert readings.scalar('object').status is DisplayStatus.INVALID
    assert readings.text('object').status is DisplayStatus.INVALID
    assert readings.json('absent').status is DisplayStatus.NOT_MAPPED


def test_invalid_json_contract_remains_invalid():
    readings = read_component_latest(
        _store({'wrong_kind': _entry('text'), 'wrong_payload': _entry(1, kind='json')})
    )
    assert readings.json('wrong_kind').status is DisplayStatus.INVALID
    assert readings.json('wrong_payload').status is DisplayStatus.INVALID


def test_system_store_validates_identity_and_keeps_typed_values():
    store = {
        'tool_key': 'operations',
        'destination_key': 'global_indicators',
        **_store({'boolean': _entry(True)}),
    }
    readings = read_system_latest(
        store, tool_key='operations', destination_key='global_indicators'
    )
    assert readings.scalar('boolean', allow_bool=True).value is True
    assert read_system_latest(
        store, tool_key='wrong', destination_key='global_indicators'
    ).source_status is DisplayStatus.INVALID
    assert read_system_latest(
        store, tool_key='operations', destination_key='wrong'
    ).source_status is DisplayStatus.INVALID
    assert read_system_latest(
        {'latest': store['latest']}, tool_key='operations', destination_key='global_indicators'
    ).source_status is DisplayStatus.INVALID


def test_system_store_without_latest_matches_empty_source():
    readings = read_system_latest(
        {'tool_key': 'operations', 'destination_key': 'global_indicators', 'latest': None},
        tool_key='operations',
        destination_key='global_indicators',
    )
    assert readings.source_status is DisplayStatus.NOT_MAPPED
    assert readings.scalar('unavailable').status is DisplayStatus.NOT_MAPPED


@pytest.mark.parametrize('key', ['', ' missing', 'missing ', 23, None])
def test_invalid_kpi_keys_raise_clear_errors(key):
    readings = read_component_latest(_store({}))
    with pytest.raises(ValueError, match='KPI key'):
        readings.scalar(key)


@pytest.mark.parametrize(('tool_key', 'destination_key'), [('', 'x'), ('x', ''), (' x', 'y')])
def test_invalid_system_binding_keys_are_rejected(tool_key, destination_key):
    with pytest.raises(ValueError):
        read_system_latest({}, tool_key=tool_key, destination_key=destination_key)


def test_reading_contract_invariants():
    with pytest.raises(ValueError, match='OK source'):
        DashboardLatestReadings(None, DisplayStatus.OK)
    with pytest.raises(ValueError, match='Degraded source'):
        DashboardLatestReadings({}, DisplayStatus.INVALID)
    with pytest.raises(TypeError, match='source_status'):
        DashboardLatestReadings({}, 'ok')
