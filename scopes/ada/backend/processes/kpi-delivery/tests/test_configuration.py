from __future__ import annotations

import pytest

from ada.processes.kpi_delivery.configuration import KpiDeliveryConfigurationRepository
from ada.processes.kpi_delivery.errors import KpiDeliveryConfigurationError


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
        'id': 'kpis',
        'partition_key': 'kpis',
        'document_type': 'ada_kpi_configuration_projection',
        'schema_version': 1,
        'revision': 'config-r1',
        'tool_projection_revision': 'tools-r1',
        'configuration': {
            'bindings': [
                {
                    'key': 'produccion_total',
                    'destination_keys': ['global_indicators', 'molienda'],
                    'latest_enabled': True,
                    'series_enabled': True,
                    'series_hours': 3,
                }
            ]
        },
    }


def test_configuration_repository_reads_exact_item_and_parses_contract() -> None:
    cosmos = CosmosStub(_document())
    repository = KpiDeliveryConfigurationRepository(
        client=cosmos,
        container_name='config-container',
        item_id='kpis',
        partition_key='kpis',
    )

    configuration = repository.read()

    assert cosmos.calls == 1
    assert cosmos.arguments == {
        'container_name': 'config-container',
        'item_id': 'kpis',
        'partition_key': 'kpis',
    }
    assert configuration.revision == 'config-r1'
    assert configuration.tool_projection_revision == 'tools-r1'
    assert configuration.bindings[0].destination_keys == ('global_indicators', 'molienda')
    assert configuration.bindings[0].series_hours == 3


def test_configuration_repository_fails_when_document_is_missing() -> None:
    repository = KpiDeliveryConfigurationRepository(
        client=CosmosStub(None),
        container_name='config-container',
        item_id='kpis',
        partition_key='kpis',
    )

    with pytest.raises(KpiDeliveryConfigurationError, match='was not found'):
        repository.read()


def test_configuration_repository_rejects_extra_fields() -> None:
    document = _document()
    document['unexpected'] = True
    repository = KpiDeliveryConfigurationRepository(
        client=CosmosStub(document),
        container_name='config-container',
        item_id='kpis',
        partition_key='kpis',
    )

    with pytest.raises(KpiDeliveryConfigurationError, match='unexpected or missing fields'):
        repository.read()


def test_configuration_repository_rejects_invalid_binding() -> None:
    document = _document()
    document['configuration']['bindings'][0]['destination_keys'] = []
    repository = KpiDeliveryConfigurationRepository(
        client=CosmosStub(document),
        container_name='config-container',
        item_id='kpis',
        partition_key='kpis',
    )

    with pytest.raises(KpiDeliveryConfigurationError, match='at least one destination'):
        repository.read()
