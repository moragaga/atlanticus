import json

from ada.kpis.connections import read_connection_registry
from ada.processes.kpi_materialization.bootstrap import load_configuration


def test_local_configuration_resolves_dynamic_connection_variables(tmp_path):
    config = tmp_path / 'config'
    config.mkdir()
    (config / 'connections.json').write_text(
        json.dumps(
            {
                'schema_version': 1,
                'connections': {
                    'tool_a': {
                        'endpoint_var': 'TOOL_A_ENDPOINT',
                        'database_var': 'TOOL_A_DATABASE',
                        'credential_var': 'TOOL_A_KEY',
                    }
                },
            }
        ),
        encoding='utf-8',
    )
    registry = read_connection_registry(tmp_path)
    configuration = load_configuration(
        process_root=tmp_path,
        registry=registry,
        environ={
            'ENVIRONMENT': 'local',
            'APPLICATION': 'ada-kpi-materialization-local',
            'VOLUMEN_PATH': str(tmp_path.resolve()),
            'POLL_INTERVAL_SECONDS': '30',
            'TOOL_A_ENDPOINT': 'http://localhost:8081',
            'TOOL_A_DATABASE': 'ada',
            'TOOL_A_KEY': 'local-key',
        },
    )

    assert configuration.require('TOOL_A_DATABASE') == 'ada'
    assert 'TOOL_A_KEY' in configuration.sensitive_keys
