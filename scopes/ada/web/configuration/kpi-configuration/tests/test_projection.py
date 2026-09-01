from datetime import UTC, datetime

from ada.configuration.kpi_configuration import (
    KpiConfiguration,
    KpiConfigurationBinding,
    KpiConfigurationProjection,
    build_kpi_configuration_projection_revision,
)


def _projection() -> KpiConfigurationProjection:
    return KpiConfigurationProjection.create(
        configuration=KpiConfiguration(
            (
                KpiConfigurationBinding(
                    kpi_key='throughput',
                    destination_keys=('global_indicators', 'crusher'),
                    latest_enabled=True,
                    series_enabled=True,
                    series_hours=4,
                ),
            )
        ),
        source_revision='source-r1',
        tool_projection_revision='tool-r1',
        projected_by='admin',
        projected_at_utc=datetime(2026, 9, 1, tzinfo=UTC),
    )


def test_delivery_document_matches_backend_projection_schema_v1() -> None:
    document = _projection().to_delivery_document(
        item_id='kpis',
        partition_key='kpis',
    )
    assert set(document) == {
        'id',
        'partition_key',
        'document_type',
        'schema_version',
        'revision',
        'tool_projection_revision',
        'configuration',
    }
    assert document['document_type'] == 'ada_kpi_configuration_projection'
    assert document['schema_version'] == 1
    assert document['configuration'] == {
        'bindings': [
            {
                'key': 'throughput',
                'destination_keys': ['global_indicators', 'crusher'],
                'latest_enabled': True,
                'series_enabled': True,
                'series_hours': 4,
            }
        ]
    }
    assert 'source_revision' not in document
    assert 'projected_by' not in document
    assert 'projected_at_utc' not in document


def test_projection_revision_changes_when_tool_revision_changes() -> None:
    first = build_kpi_configuration_projection_revision(
        source_revision='source-r1',
        tool_projection_revision='tool-r1',
    )
    second = build_kpi_configuration_projection_revision(
        source_revision='source-r1',
        tool_projection_revision='tool-r2',
    )
    assert first != second
