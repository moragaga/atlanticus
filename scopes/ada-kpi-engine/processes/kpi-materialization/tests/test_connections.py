import json

import pytest

from ada.processes.kpi_materialization.connections import (
    KpiMaterializationConnectionsError,
    read_connection_registry,
)
from atlanticus.kernel import Environment


def _write(tmp_path, connections):
    root = tmp_path / 'config'
    root.mkdir()
    (root / 'connections.json').write_text(
        json.dumps({'schema_version': 1, 'connections': connections}),
        encoding='utf-8',
    )


def test_connections_are_keyed_by_tool_key(tmp_path):
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
    specs = registry.configuration_specs()
    assert {item.key for item in specs if item.sensitive} == {'TOOL_A_KEY', 'TOOL_B_KEY'}
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
    assert resolved['tool_b'].allow_insecure_http


def test_connections_file_is_required(tmp_path):
    with pytest.raises(KpiMaterializationConnectionsError, match='required'):
        read_connection_registry(tmp_path)


def test_connection_key_must_match_tool_key_contract(tmp_path):
    _write(
        tmp_path,
        {
            'tool-a': {
                'endpoint_var': 'TOOL_ENDPOINT',
                'database_var': 'TOOL_DATABASE',
                'credential_var': 'TOOL_KEY',
            }
        },
    )

    with pytest.raises(KpiMaterializationConnectionsError, match='tool_key'):
        read_connection_registry(tmp_path)


def test_empty_connections_are_rejected(tmp_path):
    _write(tmp_path, {})

    with pytest.raises(KpiMaterializationConnectionsError, match='invalid'):
        read_connection_registry(tmp_path)


def test_connection_cannot_reuse_variable_roles(tmp_path):
    _write(
        tmp_path,
        {
            'tool_a': {
                'endpoint_var': 'SHARED',
                'database_var': 'SHARED',
                'credential_var': 'TOOL_KEY',
            }
        },
    )

    with pytest.raises(KpiMaterializationConnectionsError, match='different connection roles'):
        read_connection_registry(tmp_path)


def test_duplicate_json_keys_are_rejected(tmp_path):
    root = tmp_path / 'config'
    root.mkdir()
    (root / 'connections.json').write_text(
        '{"schema_version":1,"connections":{"tool_a":{},"tool_a":{}}}',
        encoding='utf-8',
    )

    with pytest.raises(KpiMaterializationConnectionsError, match='duplicate'):
        read_connection_registry(tmp_path)
