from datetime import UTC, datetime

import pytest

from ada.configuration.kpi_definition import (
    KPI_DEFINITION_PROJECTION_DOCUMENT_TYPE,
    KPI_DEFINITION_PROJECTION_SCHEMA_VERSION,
    KpiDefinition,
    KpiDefinitionConfiguration,
    KpiDefinitionProjection,
    KpiDefinitionProjectionError,
    KpiDefinitionSourceDocument,
)


def _source() -> KpiDefinitionSourceDocument:
    configuration = KpiDefinitionConfiguration(
        (KpiDefinition(kpi_key='transported_total', fields={'description': 'Transportado'}),)
    )
    return KpiDefinitionSourceDocument.create(
        configuration=configuration,
        saved_by='author',
        saved_at_utc=datetime(2026, 8, 27, 16, 0, tzinfo=UTC),
    )


def test_projection_create_and_roundtrip_preserve_source_configuration() -> None:
    source = _source()
    projection = KpiDefinitionProjection.create(
        configuration=source.configuration,
        source_revision=source.revision,
        projected_by='projector',
        projected_at_utc=datetime(2026, 8, 27, 17, 0, tzinfo=UTC),
    )

    document = projection.to_document(item_id='kpi-definitions', partition_key='definitions')
    restored = KpiDefinitionProjection.from_document(document)

    assert document['document_type'] == KPI_DEFINITION_PROJECTION_DOCUMENT_TYPE
    assert document['schema_version'] == KPI_DEFINITION_PROJECTION_SCHEMA_VERSION
    assert restored == projection
    assert restored.configuration == source.configuration


def test_projection_identity_is_supplied_by_repository_boundary() -> None:
    source = _source()
    projection = KpiDefinitionProjection.create(
        configuration=source.configuration,
        source_revision=source.revision,
        projected_by='projector',
        projected_at_utc=datetime(2026, 8, 27, 17, 0, tzinfo=UTC),
    )

    with pytest.raises(
        KpiDefinitionProjectionError,
        match='KPI definition projection identity must not be empty',
    ):
        projection.to_document(item_id='', partition_key='definitions')


def test_projection_rejects_revision_mismatch() -> None:
    source = _source()

    with pytest.raises(
        KpiDefinitionProjectionError,
        match='KPI definition projection revision does not match metadata',
    ):
        KpiDefinitionProjection(
            configuration=source.configuration,
            revision='wrong',
            source_revision=source.revision,
            projected_by='projector',
            projected_at_utc=datetime(2026, 8, 27, 17, 0, tzinfo=UTC),
        )


def test_projection_rejects_wrong_document_type_or_schema() -> None:
    source = _source()
    projection = KpiDefinitionProjection.create(
        configuration=source.configuration,
        source_revision=source.revision,
        projected_by='projector',
        projected_at_utc=datetime(2026, 8, 27, 17, 0, tzinfo=UTC),
    )
    document = projection.to_document(item_id='kpi-definitions', partition_key='definitions')

    with pytest.raises(KpiDefinitionProjectionError, match='document type is invalid'):
        KpiDefinitionProjection.from_document(document | {'document_type': 'wrong'})
    with pytest.raises(KpiDefinitionProjectionError, match='schema version is invalid'):
        KpiDefinitionProjection.from_document(document | {'schema_version': 99})


def test_projection_rejects_naive_timestamp() -> None:
    source = _source()

    with pytest.raises(
        KpiDefinitionProjectionError,
        match='KPI definition projection timestamp must be timezone-aware',
    ):
        KpiDefinitionProjection.create(
            configuration=source.configuration,
            source_revision=source.revision,
            projected_by='projector',
            projected_at_utc=datetime(2026, 8, 27, 17, 0),
        )
