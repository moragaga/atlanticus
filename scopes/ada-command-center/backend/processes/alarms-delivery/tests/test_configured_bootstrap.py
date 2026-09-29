from __future__ import annotations

import json

import pytest

from ada_command_center.processes.alarms_delivery import bootstrap
from ada_command_center.processes.alarms_delivery.settings import AlarmDeliverySettings


def _prepared(tmp_path):
    config = tmp_path / 'config'
    config.mkdir()
    (config / 'connections.json').write_text(
        json.dumps(
            {
                'schema_version': 1,
                'connections': {
                    'cosmos-example': {
                        'endpoint_var': 'TEST_ENDPOINT',
                        'database_var': 'TEST_DATABASE',
                        'credential_var': 'TEST_KEY',
                    }
                },
            }
        ),
        encoding='utf-8',
    )
    return {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'alarms-delivery-test',
        'VOLUMEN_PATH': str(tmp_path),
        'ALARM_CONFIGURATION_SOURCE_KEY': 'source',
        'ALARM_DELIVERY_MAX_WORKERS': '2',
        'TEST_ENDPOINT': 'http://localhost:8081',
        'TEST_DATABASE': 'ada',
        'TEST_KEY': 'example-test-key',
    }


def test_missing_connections_exits_before_runtime_bootstrap(tmp_path):
    assert bootstrap.run(process_root=tmp_path, environ={}) is None


def test_dynamic_connection_variables_are_loaded_once(tmp_path):
    values = _prepared(tmp_path)
    resolved = bootstrap.load_configuration(process_root=tmp_path, environ=values)
    assert resolved.require('TEST_DATABASE') == 'ada'
    assert 'TEST_KEY' in resolved.sensitive_keys
    settings = AlarmDeliverySettings.from_configuration(resolved)
    assert settings.max_workers == 2
    assert settings.poll_seconds == 5


def test_invalid_workers_are_rejected_before_execution(tmp_path):
    values = _prepared(tmp_path)
    values['ALARM_DELIVERY_MAX_WORKERS'] = '0'
    resolved = bootstrap.load_configuration(process_root=tmp_path, environ=values)
    with pytest.raises(ValueError, match='MAX_WORKERS'):
        AlarmDeliverySettings.from_configuration(resolved)


def test_invalid_configured_file_is_not_a_disabled_execution(tmp_path):
    _prepared(tmp_path)
    (tmp_path / 'config' / 'connections.json').write_text('[]', encoding='utf-8')
    with pytest.raises(ValueError, match='Connections document'):
        bootstrap.run(process_root=tmp_path, environ={})
