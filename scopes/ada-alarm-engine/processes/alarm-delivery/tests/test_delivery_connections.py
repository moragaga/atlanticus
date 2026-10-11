from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from ada.processes.alarm_delivery.connections import (
    AlarmDeliveryConnectionError,
    read_connection_registry,
)


def _registry():
    return {
        'schema_version': 1,
        'connections': {
            'tool_a': {
                'endpoint_var': 'TOOL_A_ENDPOINT',
                'database_var': 'TOOL_A_DATABASE',
                'credential_var': 'TOOL_A_KEY',
            },
            'tool_b': {
                'endpoint_var': 'TOOL_B_ENDPOINT',
                'database_var': 'TOOL_B_DATABASE',
                'credential_var': 'TOOL_B_KEY',
            },
        },
    }


def test_connection_registry_resolves_named_destinations(tmp_path):
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/connections.json').write_text(json.dumps(_registry()))
    registry = read_connection_registry(tmp_path)
    assert [item.tool_key for item in registry.declarations] == ['tool_a', 'tool_b']
    assert {spec.key for spec in registry.specs()} == {
        'TOOL_A_ENDPOINT',
        'TOOL_A_DATABASE',
        'TOOL_A_KEY',
        'TOOL_B_ENDPOINT',
        'TOOL_B_DATABASE',
        'TOOL_B_KEY',
    }
    assert {spec.key for spec in registry.specs() if spec.sensitive} == {'TOOL_A_KEY', 'TOOL_B_KEY'}
    values = {}
    for key in ('A', 'B'):
        values[f'TOOL_{key}_ENDPOINT'] = f'https://tool-{key.lower()}.documents.azure.com'
        values[f'TOOL_{key}_DATABASE'] = f'database-{key.lower()}'
        values[f'TOOL_{key}_KEY'] = 'private-value'
    connections = registry.resolve(values=values, environment=SimpleNamespace(is_local=False))
    assert set(connections) == {'tool_a', 'tool_b'}
    assert connections['tool_a'].database_name == 'database-a'
    assert connections['tool_b'].database_name == 'database-b'


def test_connection_registry_rejects_missing_or_duplicate_file(tmp_path):
    with pytest.raises(AlarmDeliveryConnectionError, match='required'):
        read_connection_registry(tmp_path)
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/connections.json').write_text(
        '{"schema_version":1,"schema_version":1,"connections":{}}'
    )
    with pytest.raises(AlarmDeliveryConnectionError, match='Duplicate'):
        read_connection_registry(tmp_path)


def test_connection_registry_rejects_role_collision_and_unknown_tool_format(tmp_path):
    (tmp_path / 'config').mkdir()
    value = _registry()
    value['connections']['tool_b']['database_var'] = 'TOOL_A_KEY'
    (tmp_path / 'config/connections.json').write_text(json.dumps(value))
    with pytest.raises(AlarmDeliveryConnectionError, match='roles'):
        read_connection_registry(tmp_path)
    value = _registry()
    value['connections']['Tool B'] = value['connections'].pop('tool_b')
    (tmp_path / 'config/connections.json').write_text(json.dumps(value))
    with pytest.raises(AlarmDeliveryConnectionError, match='Tool connection'):
        read_connection_registry(tmp_path)


def test_connections_reject_two_tools_in_same_cosmos_database(tmp_path):
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/connections.json').write_text(json.dumps(_registry()))
    registry = read_connection_registry(tmp_path)
    values = {
        'TOOL_A_ENDPOINT': 'https://account.example.com',
        'TOOL_A_DATABASE': 'db-shared',
        'TOOL_A_KEY': 'private-value',
        'TOOL_B_ENDPOINT': 'https://account.example.com',
        'TOOL_B_DATABASE': 'db-shared',
        'TOOL_B_KEY': 'private-value',
    }
    with pytest.raises(AlarmDeliveryConnectionError, match='own Cosmos database'):
        registry.resolve(values=values, environment=SimpleNamespace(is_local=False))
