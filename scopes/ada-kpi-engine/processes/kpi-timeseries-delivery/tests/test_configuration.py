from __future__ import annotations

import pytest

from ada.processes.kpi_timeseries_delivery.configuration import (
    KPI_REGISTRY_ITEM_ID,
    KpiTimeseriesRegistryRepository,
)
from ada.processes.kpi_timeseries_delivery.errors import (
    KpiTimeseriesDeliveryConfigurationError,
)
from ada.processes.kpi_timeseries_delivery.storage import KPI_REGISTRY_CONTAINER_SPEC


class CosmosStub:
    def __init__(self, document) -> None:
        self.document = document
        self.arguments = None

    def find_item(self, **kwargs):
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
                    'destination_keys': ['global_indicators'],
                    'latest_enabled': True,
                    'series_enabled': True,
                    'series_hours': 6,
                }
            ]
        },
    }


def test_registry_repository_preserves_timeseries_settings() -> None:
    cosmos = CosmosStub(_document())
    repository = KpiTimeseriesRegistryRepository(client=cosmos)

    configuration = repository.read()

    assert cosmos.arguments == {
        'container_name': KPI_REGISTRY_CONTAINER_SPEC.name,
        'item_id': KPI_REGISTRY_ITEM_ID,
        'partition_key': 'kpis',
    }
    assert configuration.revision == 'config-r1'
    assert configuration.tool_projection_revision == 'tools-r1'
    assert configuration.bindings[0].key == 'produccion_total'
    assert configuration.bindings[0].series_enabled is True
    assert configuration.bindings[0].series_hours == 6


def test_registry_repository_rejects_legacy_projection() -> None:
    document = _document()
    document['document_type'] = 'ada_kpi_configuration_projection'

    with pytest.raises(KpiTimeseriesDeliveryConfigurationError, match='document_type is invalid'):
        KpiTimeseriesRegistryRepository(client=CosmosStub(document)).read()


def test_registry_repository_fails_when_projection_is_missing() -> None:
    with pytest.raises(
        KpiTimeseriesDeliveryConfigurationError,
        match='Registry projection was not found',
    ):
        KpiTimeseriesRegistryRepository(client=CosmosStub(None)).read()


def test_registry_repository_rejects_invalid_schema() -> None:
    document = _document()
    document['schema_version'] = 2

    with pytest.raises(KpiTimeseriesDeliveryConfigurationError, match='schema_version is invalid'):
        KpiTimeseriesRegistryRepository(client=CosmosStub(document)).read()
