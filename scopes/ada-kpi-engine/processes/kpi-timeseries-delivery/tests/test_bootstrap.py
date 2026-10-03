import json

from ada.kpis.connections import read_connection_registry
from ada.processes.kpi_timeseries_delivery.bootstrap import load_configuration


def test_local_bootstrap_resolves_multiple_named_tool_connections(tmp_path):
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
                    },
                    'tool_b': {
                        'endpoint_var': 'TOOL_B_ENDPOINT',
                        'database_var': 'TOOL_B_DATABASE',
                        'credential_var': 'TOOL_B_KEY',
                    },
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
            'APPLICATION': 'ada-kpi-timeseries-delivery-local',
            'VOLUMEN_PATH': str(tmp_path.resolve()),
            'KPI_HISTORIAN_APPLICATION': 'ada-kpi-historian-local',
            'KPI_TIMESERIES_DELIVERY_POLL_INTERVAL_SECONDS': '1',
            'KPI_TIMESERIES_DELIVERY_MAX_WORKERS': '2',
            'TOOL_A_ENDPOINT': 'http://localhost:8081',
            'TOOL_A_DATABASE': 'ada-a',
            'TOOL_A_KEY': 'local-key-a',
            'TOOL_B_ENDPOINT': 'http://localhost:8081',
            'TOOL_B_DATABASE': 'ada-b',
            'TOOL_B_KEY': 'local-key-b',
        },
    )
    connections = registry.resolve(
        values=configuration.values,
        environment=configuration.environment,
    )

    assert tuple(connections) == ('tool_a', 'tool_b')
    assert connections['tool_a'].database_name == 'ada-a'
    assert connections['tool_b'].database_name == 'ada-b'
    assert {'TOOL_A_KEY', 'TOOL_B_KEY'} <= configuration.sensitive_keys
