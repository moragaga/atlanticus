from __future__ import annotations

import json

import pytest

from ada_command_center.processes.alarms_delivery.connections import (
    AlarmDeliveryConnectionsError,
    read_connection_registry,
)
from atlanticus.kernel import Environment


def _create(tmp_path, *, connections=None):
    root = tmp_path / 'config'
    root.mkdir(exist_ok=True)
    value = {
        'schema_version': 1,
        'connections': connections
        if connections is not None
        else {
            'cosmos-plant': {
                'endpoint_var': 'PLANT_ENDPOINT',
                'database_var': 'PLANT_DATABASE',
                'credential_var': 'PLANT_KEY',
            }
        },
    }
    (root / 'connections.json').write_text(json.dumps(value), encoding='utf-8')
    return root / 'connections.json'


def test_absent_file_disables_dispatch_without_reading_configuration(tmp_path):
    assert read_connection_registry(tmp_path) is None


def test_single_connection_resolves_only_named_variables(tmp_path):
    _create(tmp_path)
    registry = read_connection_registry(tmp_path)
    assert registry is not None
    specs = registry.configuration_specs()
    assert {entry.key for entry in specs} == {'PLANT_ENDPOINT', 'PLANT_DATABASE', 'PLANT_KEY'}
    assert {entry.key for entry in specs if entry.sensitive} == {'PLANT_KEY'}
    resolved = registry.resolve(
        values={
            'PLANT_ENDPOINT': 'http://localhost:8081',
            'PLANT_DATABASE': 'plant',
            'PLANT_KEY': 'example-only',
        },
        environment=Environment.from_value('local'),
    )
    assert set(resolved) == {'cosmos-plant'}
    assert resolved['cosmos-plant'].database_name == 'plant'
    assert resolved['cosmos-plant'].allow_insecure_http


def test_invalid_document_does_not_disable_delivery(tmp_path):
    filename = _create(tmp_path)
    filename.write_text('invalid', encoding='utf-8')
    with pytest.raises(AlarmDeliveryConnectionsError, match='could not be read'):
        read_connection_registry(tmp_path)


def test_empty_registry_is_an_error(tmp_path):
    _create(tmp_path, connections={})
    with pytest.raises(AlarmDeliveryConnectionsError, match='invalid'):
        read_connection_registry(tmp_path)


def test_duplicate_connection_keys_are_rejected(tmp_path):
    filename = _create(tmp_path)
    filename.write_text(
        '{"schema_version":1,"connections":{"a":{},"a":{}}}', encoding='utf-8'
    )
    with pytest.raises(AlarmDeliveryConnectionsError, match='duplicate keys'):
        read_connection_registry(tmp_path)


def test_symlink_cannot_replace_connection_file(tmp_path):
    filename = _create(tmp_path)
    link = filename.with_suffix('.link')
    link.symlink_to(filename)
    filename.unlink()
    filename.symlink_to(link)
    with pytest.raises(AlarmDeliveryConnectionsError, match='regular file'):
        read_connection_registry(tmp_path)


def test_unknown_and_shared_variables_fail(tmp_path):
    _create(
        tmp_path,
        connections={
            'cosmos-plant': {
                'endpoint_var': 'SHARED',
                'database_var': 'SHARED',
                'credential_var': 'PLANT_KEY',
            }
        },
    )
    with pytest.raises(AlarmDeliveryConnectionsError):
        read_connection_registry(tmp_path)
