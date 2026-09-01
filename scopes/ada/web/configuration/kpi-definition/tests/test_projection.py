from datetime import UTC, datetime

import pytest

from ada.configuration.kpi_definition import (
    KPI_DEFINITION_PROJECTION_DOCUMENT_TYPE,
    KPI_DEFINITION_PROJECTION_SCHEMA_VERSION,
    KpiDefinition,
    KpiDefinitionAuthorityCatalog,
    KpiDefinitionConfiguration,
    KpiDefinitionCoverageStatus,
    KpiDefinitionProjection,
    KpiDefinitionProjectionError,
    KpiDefinitionSourceDocument,
)


def _source() -> KpiDefinitionSourceDocument:
    return KpiDefinitionSourceDocument.create(
        configuration=KpiDefinitionConfiguration(
            (
                KpiDefinition(
                    kpi_key='transported_total',
                    fields={'description': 'Transportado'},
                ),
            )
        ),
        saved_by='author',
        saved_at_utc=datetime(2026, 9, 1, 16, 0, tzinfo=UTC),
    )


def _authority(revision='kpi-config-r1') -> KpiDefinitionAuthorityCatalog:
    return KpiDefinitionAuthorityCatalog(
        kpi_configuration_revision=revision,
        kpi_keys=('transported_total', 'recovery'),
    )


def _projection(
    *,
    authority: KpiDefinitionAuthorityCatalog | None = None,
) -> KpiDefinitionProjection:
    source = _source()
    return KpiDefinitionProjection.create(
        configuration=source.configuration,
        source_revision=source.revision,
        authority=authority or _authority(),
        projected_by='projector',
        projected_at_utc=datetime(2026, 9, 1, 17, 0, tzinfo=UTC),
    )


def test_projection_schema_v2_roundtrip_preserves_authority_and_coverage() -> None:
    projection = _projection()
    document = projection.to_document(
        item_id='kpi-definitions',
        partition_key='definitions',
    )
    restored = KpiDefinitionProjection.from_document(document)

    assert document['document_type'] == KPI_DEFINITION_PROJECTION_DOCUMENT_TYPE
    assert document['schema_version'] == KPI_DEFINITION_PROJECTION_SCHEMA_VERSION == 2
    assert restored == projection
    assert restored.kpi_configuration_revision == 'kpi-config-r1'
    assert restored.coverage[0].status is KpiDefinitionCoverageStatus.DEFINED
    assert restored.coverage[1].status is KpiDefinitionCoverageStatus.MISSING


def test_projection_revision_depends_on_source_and_kpi_configuration() -> None:
    first = _projection(authority=_authority('kpi-config-r1'))
    second = _projection(authority=_authority('kpi-config-r2'))

    assert first.revision != second.revision


def test_projection_identity_is_supplied_by_repository_boundary() -> None:
    projection = _projection()

    with pytest.raises(
        KpiDefinitionProjectionError,
        match='item id must not be empty',
    ):
        projection.to_document(item_id='', partition_key='definitions')


def test_projection_rejects_schema_v1_instead_of_keeping_legacy_adapter() -> None:
    document = _projection().to_document(
        item_id='kpi-definitions',
        partition_key='definitions',
    )

    with pytest.raises(
        KpiDefinitionProjectionError,
        match='schema version is invalid',
    ):
        KpiDefinitionProjection.from_document(document | {'schema_version': 1})


def test_projection_rejects_naive_timestamp() -> None:
    source = _source()

    with pytest.raises(
        KpiDefinitionProjectionError,
        match='timestamp must be timezone-aware',
    ):
        KpiDefinitionProjection.create(
            configuration=source.configuration,
            source_revision=source.revision,
            authority=_authority(),
            projected_by='projector',
            projected_at_utc=datetime(2026, 9, 1, 17, 0),
        )
