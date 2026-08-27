from datetime import UTC, datetime

import pytest

from ada.configuration.kpi_definition import (
    KPI_DEFINITION_SOURCE_DOCUMENT_TYPE,
    KPI_DEFINITION_SOURCE_SCHEMA_VERSION,
    KpiDefinition,
    KpiDefinitionConfiguration,
    KpiDefinitionSourceDocument,
    KpiDefinitionValidationError,
    build_kpi_definition_digest,
)


def _configuration() -> KpiDefinitionConfiguration:
    return KpiDefinitionConfiguration(
        (
            KpiDefinition(
                kpi_key='transported_total',
                fields={'description': 'Material transportado', 'unit': 'kt'},
            ),
        )
    )


def test_source_create_builds_content_revision_and_utc_audit() -> None:
    occurred_at = datetime(2026, 8, 27, 17, 0, tzinfo=UTC)
    configuration = _configuration()

    source = KpiDefinitionSourceDocument.create(
        configuration=configuration,
        saved_by=' user@contoso.com ',
        saved_at_utc=occurred_at,
    )

    assert source.revision == build_kpi_definition_digest(configuration)
    assert source.saved_by == 'user@contoso.com'
    assert source.saved_at_utc == occurred_at


def test_source_document_roundtrip_uses_dedicated_contract() -> None:
    source = KpiDefinitionSourceDocument.create(
        configuration=_configuration(),
        saved_by='owner',
        saved_at_utc=datetime(2026, 8, 27, 17, 0, tzinfo=UTC),
    )

    document = source.to_document()
    restored = KpiDefinitionSourceDocument.from_document(document)

    assert document['document_type'] == KPI_DEFINITION_SOURCE_DOCUMENT_TYPE
    assert document['schema_version'] == KPI_DEFINITION_SOURCE_SCHEMA_VERSION
    assert restored == source


def test_source_digest_is_deterministic_for_field_order() -> None:
    first = KpiDefinitionConfiguration((KpiDefinition(kpi_key='kpi', fields={'a': '1', 'b': '2'}),))
    second = KpiDefinitionConfiguration(
        (KpiDefinition(kpi_key='kpi', fields={'b': '2', 'a': '1'}),)
    )

    assert build_kpi_definition_digest(first) == build_kpi_definition_digest(second)


def test_source_rejects_revision_mismatch() -> None:
    with pytest.raises(
        KpiDefinitionValidationError,
        match='KPI definition source revision does not match content',
    ):
        KpiDefinitionSourceDocument(
            configuration=_configuration(),
            revision='wrong',
            saved_by='owner',
            saved_at_utc=datetime(2026, 8, 27, 17, 0, tzinfo=UTC),
        )


def test_source_rejects_naive_timestamp() -> None:
    configuration = _configuration()

    with pytest.raises(
        KpiDefinitionValidationError,
        match='KPI definition source audit timestamp must be timezone-aware',
    ):
        KpiDefinitionSourceDocument(
            configuration=configuration,
            revision=build_kpi_definition_digest(configuration),
            saved_by='owner',
            saved_at_utc=datetime(2026, 8, 27, 17, 0),
        )


def test_source_rejects_wrong_document_type_or_schema() -> None:
    source = KpiDefinitionSourceDocument.create(
        configuration=_configuration(),
        saved_by='owner',
        saved_at_utc=datetime(2026, 8, 27, 17, 0, tzinfo=UTC),
    )
    wrong_type = source.to_document() | {'document_type': 'wrong'}
    wrong_schema = source.to_document() | {'schema_version': 99}

    with pytest.raises(KpiDefinitionValidationError, match='document type is invalid'):
        KpiDefinitionSourceDocument.from_document(wrong_type)
    with pytest.raises(KpiDefinitionValidationError, match='schema version is invalid'):
        KpiDefinitionSourceDocument.from_document(wrong_schema)
