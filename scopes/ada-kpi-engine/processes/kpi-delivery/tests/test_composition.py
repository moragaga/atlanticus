from ada.kpis.materialization import (
    LocalKpiRegistryStore,
    materialization_root,
    materialize_registry,
)
from ada.processes.kpi_delivery.composition import build_composition
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.connectivity.cosmos import CosmosSettings
from atlanticus.kernel import Environment


def _projection():
    from ada.kpis.materialization import KPI_REGISTRY_ITEM_ID

    return {
        'id': KPI_REGISTRY_ITEM_ID,
        'partition_key': 'kpis',
        'document_type': 'ada_kpi_registry_projection_record',
        'schema_version': 1,
        'source_key': 'kpis',
        'source_release_id': 'registry-r1',
        'source_published_at_utc': '2026-10-02T12:00:00+00:00',
        'projected_at_utc': '2026-10-02T12:00:01+00:00',
        'dependencies': [
            {
                'source_key': 'tools',
                'source_release_id': 'tools-r1',
                'source_published_at_utc': '2026-10-02T11:59:00+00:00',
                'dependencies': [],
            }
        ],
        'payload': {
            'bindings': [
                {
                    'kpi_key': 'produccion_total',
                    'destination_keys': ['global_indicators'],
                    'latest_enabled': True,
                    'series_enabled': False,
                    'series_hours': None,
                }
            ]
        },
    }


def _configuration(tmp_path):
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-delivery-local',
        'VOLUMEN_PATH': str(tmp_path.resolve()),
        'KPI_RUNTIME_APPLICATION': 'ada-kpi-runtime-local',
        'POLL_INTERVAL_SECONDS': '1',
        'KPI_DELIVERY_MAX_WORKERS': '2',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_composition_freezes_local_registries_and_builds_parallel_tool_publishers(tmp_path):
    store = LocalKpiRegistryStore(root=materialization_root(tmp_path.resolve()))
    store.replace(
        tool_key='tool_a',
        document=materialize_registry(
            tool_key='tool_a',
            projection=_projection(),
        ),
    )
    connections = {
        'tool_a': CosmosSettings(
            endpoint='http://localhost:8081',
            database_name='ada-a',
            key='local-key',
            allow_insecure_http=True,
        )
    }

    composition = build_composition(
        configuration=_configuration(tmp_path),
        connections=connections,
    )
    try:
        assert tuple(composition.frozen_configurations) == ('tool_a',)
        assert tuple(composition.publishers) == ('tool_a',)
        assert tuple(composition.clients) == ('tool_a',)
        assert composition.parallel_publisher is not None
        assert composition.definition.sleep_seconds == 1
        assert composition.evaluations.paths.application_root == (
            tmp_path / 'ada-kpi-runtime-local'
        )
    finally:
        composition.parallel_publisher.close()
