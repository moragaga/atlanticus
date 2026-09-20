from __future__ import annotations

import pytest

from ada.processes.kpi_delivery.configuration import (
    KPI_REGISTRY_ITEM_ID,
    KpiDeliveryRegistryRepository,
)
from ada.processes.kpi_delivery.errors import KpiDeliveryConfigurationError
from ada.processes.kpi_delivery.storage import KPI_REGISTRY_CONTAINER_SPEC


class CosmosStub:
    def __init__(self, document) -> None:
        self.document = document
        self.calls = 0
        self.arguments = None

    def find_item(self, **kwargs):
        self.calls += 1
        self.arguments = kwargs
        return self.document


def _document() -> dict[str, object]:
    return {
        'id': KPI_REGISTRY_ITEM_ID,
        'partition_key': 'kpis',
        'document_type': 'ada_kpi_registry_projection_record',
        'schema_version': 1,
        'source_key': 'kpis',
        'source_release_id': 'config-r1',
        'source_published_at_utc': '2026-09-20T20:00:00+00:00',
        'projected_at_utc': '2026-09-20T20:01:00+00:00',
        'dependencies': [
            {
                'source_key': 'tools',
                'source_release_id': 'tools-r1',
                'source_published_at_utc': '2026-09-20T19:00:00+00:00',
                'dependencies': [],
            }
        ],
        'payload': {
            'bindings': [
                {
                    'kpi_key': 'produccion_total',
                    'destination_keys': ['global_indicators', 'molienda'],
                    'latest_enabled': True,
                    'series_enabled': True,
                    'series_hours': 3,
                }
            ]
        },
    }


def test_registry_repository_reads_current_projection_and_builds_effective_configuration() -> None:
    cosmos = CosmosStub(_document())
    repository = KpiDeliveryRegistryRepository(client=cosmos)

    configuration = repository.read()

    assert cosmos.calls == 1
    assert cosmos.arguments == {
        'container_name': KPI_REGISTRY_CONTAINER_SPEC.name,
        'item_id': KPI_REGISTRY_ITEM_ID,
        'partition_key': 'kpis',
    }
    assert configuration.revision == 'config-r1'
    assert configuration.tool_projection_revision == 'tools-r1'
    assert configuration.bindings[0].key == 'produccion_total'
    assert configuration.bindings[0].destination_keys == ('global_indicators', 'molienda')
    assert configuration.bindings[0].series_hours == 3


def test_registry_repository_fails_when_projection_is_missing() -> None:
    repository = KpiDeliveryRegistryRepository(client=CosmosStub(None))

    with pytest.raises(KpiDeliveryConfigurationError, match='Registry projection was not found'):
        repository.read()


def test_registry_repository_rejects_legacy_configuration_projection() -> None:
    document = _document()
    document['document_type'] = 'ada_kpi_configuration_projection'
    repository = KpiDeliveryRegistryRepository(client=CosmosStub(document))

    with pytest.raises(KpiDeliveryConfigurationError, match='document_type is invalid'):
        repository.read()


def test_registry_repository_rejects_invalid_schema() -> None:
    document = _document()
    document['schema_version'] = 2
    repository = KpiDeliveryRegistryRepository(client=CosmosStub(document))

    with pytest.raises(KpiDeliveryConfigurationError, match='schema_version is invalid'):
        repository.read()


def test_registry_repository_preserves_registry_binding_semantics() -> None:
    document = _document()
    document['payload']['bindings'][0]['series_enabled'] = False
    document['payload']['bindings'][0]['series_hours'] = None
    repository = KpiDeliveryRegistryRepository(client=CosmosStub(document))

    configuration = repository.read()

    binding = configuration.bindings[0]
    assert binding.latest_enabled is True
    assert binding.series_enabled is False
    assert binding.series_hours is None


def test_registry_repository_rejects_series_hours_when_series_is_disabled() -> None:
    document = _document()
    document['payload']['bindings'][0]['series_enabled'] = False
    repository = KpiDeliveryRegistryRepository(client=CosmosStub(document))

    with pytest.raises(KpiDeliveryConfigurationError, match='must be empty'):
        repository.read()
