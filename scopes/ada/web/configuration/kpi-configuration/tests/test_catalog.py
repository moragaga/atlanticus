from datetime import UTC, datetime

from ada.configuration.kpi_configuration import (
    KpiConfiguration,
    KpiConfigurationBinding,
    KpiConfigurationProjection,
)


def projection(
    *,
    tool_revision: str = 'tool-r1',
) -> KpiConfigurationProjection:
    return KpiConfigurationProjection.create(
        configuration=KpiConfiguration(
            (
                KpiConfigurationBinding(
                    kpi_key='throughput',
                    destination_keys=('global_indicators',),
                ),
                KpiConfigurationBinding(
                    kpi_key='recovery',
                    destination_keys=('plant',),
                    series_enabled=True,
                    series_hours=4,
                ),
            )
        ),
        source_revision='source-r1',
        tool_projection_revision=tool_revision,
        projected_by='projector',
        projected_at_utc=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
    )


def test_projection_catalog_exposes_only_authoritative_kpi_identity() -> None:
    value = projection()

    catalog = value.catalog()

    assert catalog.revision == value.revision
    assert catalog.kpi_keys == ('throughput', 'recovery')
    assert catalog.keys == frozenset({'throughput', 'recovery'})


def test_catalog_revision_tracks_projection_not_only_source() -> None:
    first = projection(tool_revision='tool-r1')
    second = projection(tool_revision='tool-r2')

    assert first.source_revision == second.source_revision
    assert first.catalog().kpi_keys == second.catalog().kpi_keys
    assert first.catalog().revision != second.catalog().revision


def test_delivery_contract_is_unchanged_by_catalog_addition() -> None:
    document = projection().to_delivery_document(
        item_id='kpis',
        partition_key='kpis',
    )

    assert 'catalog' not in document
    assert document['schema_version'] == 1
    assert document['configuration']['bindings'][0]['key'] == 'throughput'
