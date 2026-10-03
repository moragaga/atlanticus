from ada.kpis.materialization import KPI_REGISTRY_ITEM_ID


def projection(*, revision: str = 'registry-r1') -> dict[str, object]:
    return {
        'id': KPI_REGISTRY_ITEM_ID,
        'partition_key': 'kpi-registry',
        'document_type': 'ada_kpi_registry_projection_record',
        'schema_version': 1,
        'source_key': 'kpi-registry',
        'source_release_id': revision,
        'source_published_at_utc': '2026-10-02T12:00:00+00:00',
        'projected_at_utc': '2026-10-02T12:00:01+00:00',
        'dependencies': [
            {
                'source_key': 'tool',
                'source_release_id': 'tool-r1',
                'source_published_at_utc': '2026-10-02T11:59:00+00:00',
                'dependencies': [],
            }
        ],
        'payload': {
            'bindings': [
                {
                    'kpi_key': 'crusher.rate',
                    'destination_keys': ['global_indicators'],
                    'latest_enabled': True,
                    'series_enabled': True,
                    'series_hours': 8,
                }
            ],
            "tool_key": "tool_operaciones_integradas_af1b7d9983bd"
        },
    }
