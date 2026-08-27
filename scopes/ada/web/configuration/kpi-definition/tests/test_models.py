from types import MappingProxyType

import pytest

from ada.configuration.kpi_definition import (
    KpiDefinition,
    KpiDefinitionConfiguration,
    KpiDefinitionValidationError,
)


def test_definition_normalizes_identity_and_field_names_without_changing_text() -> None:
    definition = KpiDefinition(
        kpi_key=' transported_total ',
        fields={' description ': '  Material transportado  ', 'owner': None},
    )

    assert definition.kpi_key == 'transported_total'
    assert definition.fields == {
        'description': '  Material transportado  ',
        'owner': None,
    }
    assert isinstance(definition.fields, MappingProxyType)


def test_definition_rejects_invalid_identity() -> None:
    with pytest.raises(KpiDefinitionValidationError, match='KPI key must be a non-empty string'):
        KpiDefinition(kpi_key=' ', fields={})


def test_definition_rejects_invalid_field_name_and_value() -> None:
    with pytest.raises(
        KpiDefinitionValidationError,
        match='KPI definition field name must be a non-empty string',
    ):
        KpiDefinition(kpi_key='kpi', fields={' ': 'value'})

    with pytest.raises(
        KpiDefinitionValidationError,
        match='KPI definition field values must be strings or null',
    ):
        KpiDefinition(kpi_key='kpi', fields={'description': 1})  # type: ignore[dict-item]


def test_definition_rejects_field_names_that_collide_after_normalization() -> None:
    with pytest.raises(
        KpiDefinitionValidationError,
        match='KPI definition field names must be unique',
    ):
        KpiDefinition(kpi_key='kpi', fields={'owner': 'A', ' owner ': 'B'})


def test_definition_document_roundtrip_preserves_arbitrary_fields() -> None:
    definition = KpiDefinition(
        kpi_key='availability',
        fields={'title': 'Disponibilidad', 'notes': 'Texto libre', 'future_field': None},
    )

    restored = KpiDefinition.from_document(definition.to_document())

    assert restored == definition


def test_configuration_allows_empty_collection_and_lookup() -> None:
    configuration = KpiDefinitionConfiguration()

    assert configuration.definitions == ()
    assert configuration.definition('missing') is None


def test_configuration_rejects_duplicate_kpi_keys() -> None:
    first = KpiDefinition(kpi_key='same', fields={'title': 'A'})
    second = KpiDefinition(kpi_key='same', fields={'title': 'B'})

    with pytest.raises(KpiDefinitionValidationError, match='KPI definition keys must be unique'):
        KpiDefinitionConfiguration((first, second))


def test_configuration_roundtrip_preserves_definition_order() -> None:
    configuration = KpiDefinitionConfiguration(
        (
            KpiDefinition(kpi_key='a', fields={'title': 'A'}),
            KpiDefinition(kpi_key='b', fields={'title': 'B'}),
        )
    )

    restored = KpiDefinitionConfiguration.from_document(configuration.to_document())

    assert restored == configuration
    assert restored.definition('b') == configuration.definitions[1]


def test_definition_allows_empty_fields_as_authoring_stub() -> None:
    definition = KpiDefinition(kpi_key='availability', fields={})

    restored = KpiDefinition.from_document(definition.to_document())

    assert dict(definition.fields) == {}
    assert restored == definition
