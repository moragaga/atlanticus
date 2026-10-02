import json

import pytest

from ada.kpis.connections import (
    KpiConnectionsError,
    read_connection_registry,
)
from atlanticus.kernel import Environment


def _write(tmp_path, connections):
    config = tmp_path / 'config'
    config.mkdir()
    (config / 'connections.json').write_text(
        json.dumps({'schema_version': 1, 'connections': connections}),
        encoding='utf-8',
    )


def test_registry_is_keyed_by_tool_and_resolves_dynamic_variables(tmp_path):
    _write(
        tmp_path,
        {
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
    )
    registry = read_connection_registry(tmp_path)

    assert tuple(item.tool_key for item in registry.declarations) == ('tool_a', 'tool_b')
    assert {item.key for item in registry.configuration_specs() if item.sensitive} == {
        'TOOL_A_KEY',
        'TOOL_B_KEY',
    }
    resolved = registry.resolve(
        values={
            'TOOL_A_ENDPOINT': 'http://localhost:8081',
            'TOOL_A_DATABASE': 'a',
            'TOOL_A_KEY': 'key-a',
            'TOOL_B_ENDPOINT': 'http://localhost:8082',
            'TOOL_B_DATABASE': 'b',
            'TOOL_B_KEY': 'key-b',
        },
        environment=Environment.from_value('local'),
    )
    assert set(resolved) == {'tool_a', 'tool_b'}
    assert resolved['tool_a'].database_name == 'a'


def test_registry_rejects_same_physical_cosmos_for_two_tools(tmp_path):
    _write(
        tmp_path,
        {
            'tool_a': {
                'endpoint_var': 'A_ENDPOINT',
                'database_var': 'A_DATABASE',
                'credential_var': 'A_KEY',
            },
            'tool_b': {
                'endpoint_var': 'B_ENDPOINT',
                'database_var': 'B_DATABASE',
                'credential_var': 'B_KEY',
            },
        },
    )
    registry = read_connection_registry(tmp_path)
    values = {
        'A_ENDPOINT': 'http://localhost:8081',
        'A_DATABASE': 'ada',
        'A_KEY': 'a',
        'B_ENDPOINT': 'http://localhost:8081',
        'B_DATABASE': 'ada',
        'B_KEY': 'b',
    }

    with pytest.raises(KpiConnectionsError, match='share the same Cosmos database'):
        registry.resolve(values=values, environment=Environment.from_value('local'))


def test_registry_requires_valid_tool_keys_and_non_empty_connections(tmp_path):
    _write(
        tmp_path,
        {
            'tool-a': {
                'endpoint_var': 'ENDPOINT',
                'database_var': 'DATABASE',
                'credential_var': 'KEY',
            }
        },
    )
    with pytest.raises(KpiConnectionsError, match='tool_key'):
        read_connection_registry(tmp_path)

    other = tmp_path / 'other'
    other.mkdir()
    _write(other, {})
    with pytest.raises(KpiConnectionsError, match='invalid'):
        read_connection_registry(other)


def test_registry_rejects_variable_role_reuse(tmp_path):
    _write(
        tmp_path,
        {
            'tool_a': {
                'endpoint_var': 'SHARED',
                'database_var': 'SHARED',
                'credential_var': 'KEY',
            }
        },
    )
    with pytest.raises(KpiConnectionsError, match='different connection roles'):
        read_connection_registry(tmp_path)
