import pytest

from ada.kpis.materialization import (
    LocalKpiRegistryStore,
    materialization_root,
    materialize_registry,
)
from ada.processes.kpi_delivery.configuration import (
    load_frozen_delivery_configurations,
)
from ada.processes.kpi_delivery.errors import KpiDeliveryConfigurationError


def _projection(revision='registry-r1'):
    from ada.kpis.materialization import KPI_REGISTRY_ITEM_ID

    return {
        'id': KPI_REGISTRY_ITEM_ID,
        'partition_key': 'kpis',
        'document_type': 'ada_kpi_registry_projection_record',
        'schema_version': 1,
        'source_key': 'kpis',
        'source_release_id': revision,
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


def _store(tmp_path):
    return LocalKpiRegistryStore(root=materialization_root(tmp_path.resolve()))


def test_frozen_configuration_reads_all_registries_once_at_start(tmp_path):
    store = _store(tmp_path)
    for tool_key, revision in (('tool_a', 'r1'), ('tool_b', 'r2')):
        store.replace(
            tool_key=tool_key,
            document=materialize_registry(
                tool_key=tool_key,
                projection=_projection(revision),
            ),
        )

    frozen = load_frozen_delivery_configurations(
        store=store,
        expected_tool_keys=('tool_a', 'tool_b'),
    )

    assert tuple(frozen) == ('tool_a', 'tool_b')
    assert frozen['tool_a'].registry_revision == 'r1'
    assert frozen['tool_b'].registry_revision == 'r2'
    assert len(frozen['tool_a'].registry_digest) == 64
    assert frozen['tool_a'].configuration.bindings[0].key == 'produccion_total'


def test_materialized_tool_set_must_match_connections_exactly(tmp_path):
    store = _store(tmp_path)
    store.replace(
        tool_key='tool_a',
        document=materialize_registry(
            tool_key='tool_a',
            projection=_projection(),
        ),
    )

    with pytest.raises(KpiDeliveryConfigurationError, match='does not match'):
        load_frozen_delivery_configurations(
            store=store,
            expected_tool_keys=('tool_a', 'tool_b'),
        )
