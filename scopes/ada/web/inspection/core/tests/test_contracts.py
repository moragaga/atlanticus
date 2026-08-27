from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ada.web.inspection.core import (
    KpiDefinition,
    KpiDefinitionProvider,
    KpiDefinitionSnapshot,
    KpiInspectionResult,
)


def test_definition_accepts_arbitrary_text_fields_without_freezing_schema() -> None:
    definition = KpiDefinition(
        kpi_key='transported_total',
        fields={
            'title': 'Transportado',
            'description': 'Tonelaje transportado durante el período.',
            'owner': 'Operations',
            'notes': None,
        },
    )

    assert definition.kpi_key == 'transported_total'
    assert dict(definition.fields) == {
        'title': 'Transportado',
        'description': 'Tonelaje transportado durante el período.',
        'owner': 'Operations',
        'notes': None,
    }


def test_definition_fields_are_immutable_and_detached_from_input_mapping() -> None:
    fields = {'title': 'Transportado'}
    definition = KpiDefinition(kpi_key='transported_total', fields=fields)

    fields['title'] = 'Changed outside'

    assert definition.fields['title'] == 'Transportado'
    with pytest.raises(TypeError):
        definition.fields['title'] = 'Changed inside'  # type: ignore[index]


def test_definition_rejects_invalid_identity_or_non_text_payload() -> None:
    with pytest.raises(ValueError, match='KPI key must be a non-empty string'):
        KpiDefinition(kpi_key=' ', fields={})
    with pytest.raises(ValueError, match='field names must be non-empty strings'):
        KpiDefinition(kpi_key='transported_total', fields={'': 'value'})
    with pytest.raises(ValueError, match='field values must be strings or null'):
        KpiDefinition(kpi_key='transported_total', fields={'description': 42})  # type: ignore[dict-item]


def test_snapshot_rejects_duplicate_keys() -> None:
    definition = KpiDefinition(kpi_key='transported_total', fields={'title': 'Transportado'})
    snapshot = KpiDefinitionSnapshot(definitions=(definition,))

    assert snapshot.definitions == (definition,)

    with pytest.raises(ValueError, match='duplicate KPI keys'):
        KpiDefinitionSnapshot(definitions=(definition, definition))


def test_provider_contract_is_satisfied_without_cosmos_or_azure_dependencies() -> None:
    snapshot = KpiDefinitionSnapshot(
        definitions=(KpiDefinition(kpi_key='transported_total', fields={'title': 'Transportado'}),)
    )

    class InMemoryProvider:
        def load_snapshot(self) -> KpiDefinitionSnapshot:
            return snapshot

    provider = InMemoryProvider()

    assert isinstance(provider, KpiDefinitionProvider)
    assert provider.load_snapshot() is snapshot


def test_inspection_result_models_available_and_unavailable_without_refresh_semantics() -> None:
    definition = KpiDefinition(kpi_key='transported_total', fields={'title': 'Transportado'})

    available = KpiInspectionResult(kpi_key='transported_total', definition=definition)
    unavailable = KpiInspectionResult(kpi_key='unknown_kpi', definition=None)

    assert available.available is True
    assert available.definition is definition
    assert unavailable.available is False
    assert unavailable.definition is None


def test_inspection_result_rejects_mismatched_identity() -> None:
    definition = KpiDefinition(kpi_key='transported_total', fields={'title': 'Transportado'})

    with pytest.raises(ValueError, match='does not match definition KPI key'):
        KpiInspectionResult(kpi_key='different_kpi', definition=definition)


def test_contracts_are_frozen() -> None:
    definition = KpiDefinition(kpi_key='transported_total', fields={'title': 'Transportado'})
    snapshot = KpiDefinitionSnapshot(definitions=(definition,))
    result = KpiInspectionResult(kpi_key='transported_total', definition=definition)

    with pytest.raises(FrozenInstanceError):
        definition.kpi_key = 'other'  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        snapshot.definitions = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.definition = None  # type: ignore[misc]
