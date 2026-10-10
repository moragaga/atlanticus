from __future__ import annotations

import pytest

from ada.web.kpis.readings import read_component_latest, read_system_latest
from ada.web.ui.display_status import DisplayStatus


def _entry(value, parsed=None, kind='value', value_type='float'):
    return {
        'status': 'ok',
        'value_kind': kind,
        'value_type': value_type,
        'value': value,
        'parsed_value': parsed,
    }


def test_text_and_scalar_use_two_backend_representations():
    store = {'latest': {'values': {'level': _entry('1234.50', '1.234,50')}}}
    readings = read_component_latest(store)
    assert readings.scalar('level').value == '1234.50'
    assert readings.text('level').value == '1.234,50'
    assert readings.value_type('level') == 'float'


def test_text_is_not_reformatted_or_trimmed():
    readings = read_component_latest(
        {'latest': {'values': {'a': _entry('  ready  ', '  ready  ', value_type='text')}}}
    )
    assert readings.text('a').value == '  ready  '
    assert readings.scalar('a').value == '  ready  '


def test_json_is_structured_and_not_scalar():
    readings = read_component_latest(
        {'latest': {'values': {'a': _entry({'rows': []}, None, 'json', None)}}}
    )
    assert readings.json('a').value == {'rows': []}
    assert readings.scalar('a').status is DisplayStatus.INVALID
    assert readings.text('a').status is DisplayStatus.INVALID


@pytest.mark.parametrize(
    'status,expect',
    [
        ('missing', DisplayStatus.EMPTY),
        ('error', DisplayStatus.ERROR),
    ],
)
def test_degraded(status, expect):
    readings = read_component_latest(
        {
            'latest': {
                'values': {
                    'x': {
                        'status': status,
                        'value_kind': 'json' if status == 'error' else None,
                        'value_type': None,
                        'value': None,
                        'parsed_value': None,
                    }
                }
            }
        }
    )
    assert readings.text('x').status is expect
    assert readings.scalar('x').status is expect
    assert readings.json('x').status is expect
    assert readings.text('absent').status is DisplayStatus.NOT_MAPPED


def test_wrong_identity_rejected_for_system_store():
    source = {
        'tool_key': 'operations',
        'destination_key': 'global_indicators',
        'latest': {'values': {}},
    }
    assert (
        read_system_latest(
            source, tool_key='operations', destination_key='global_indicators'
        ).source_status
        is DisplayStatus.OK
    )
    assert (
        read_system_latest(
            source, tool_key='different', destination_key='global_indicators'
        ).source_status
        is DisplayStatus.INVALID
    )


@pytest.mark.parametrize(
    'input,status',
    [
        (None, DisplayStatus.INVALID),
        ({}, DisplayStatus.NOT_MAPPED),
        ({'latest': []}, DisplayStatus.INVALID),
        ({'latest': {'values': {}}}, DisplayStatus.OK),
    ],
)
def test_source_states(input, status):
    assert read_component_latest(input).source_status is status
