from datetime import UTC, datetime

import pytest

from ada.web.application.configuration_manager.tool_kpi_registry_destinations import (
    ToolConfigurationKpiDestinationCatalogProvider,
)
from ada.web.kpis.registry.configuration import KpiRegistryValidationError
from ada.web.tools.configuration import ToolConfiguration
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey, SourceReleaseId


class ProjectionMemory(ProjectionStore[ToolConfiguration]):
    def __init__(self, value: ProjectionRecord[ToolConfiguration] | None = None) -> None:
        self.value = value

    def get_active(self, source_key: SourceKey):
        if self.value is None or self.value.source_key != source_key:
            return None
        return self.value

    def replace_active(self, projection):
        self.value = projection
        return projection


def tool_document() -> dict[str, object]:
    return {
        'tool_key': 'process',
        'display_name': 'Operaciones Integradas',
        'kind': 'process',
        'source_consumption': {
            'tool_key': 'process',
            'source_keys': ['pi'],
        },
        'source_operational_participation': {
            'tool_key': 'process',
            'control_sources': [
                {
                    'source_key': 'pi',
                    'pre_degrading_after_seconds': 200,
                    'degrading_after_seconds': 300,
                }
            ],
            'additional_observation_source_keys': [],
        },
        'structure': {
            'tool_key': 'process',
            'kind': 'process',
            'operational_scope': 'plant',
            'components': [
                {
                    'key': 'crusher',
                    'display_name': 'Chancado',
                    'scope': None,
                    'layout_role': 'center',
                    'subcomponents': [
                        {
                            'key': 'primary',
                            'display_name': 'Primario',
                            'linked_component_keys': [],
                        }
                    ],
                }
            ],
        },
    }


def projection(configuration: ToolConfiguration) -> ProjectionRecord[ToolConfiguration]:
    published = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    return ProjectionRecord(
        source_key=SourceKey('tools'),
        source_release_id=SourceReleaseId('tools-r1'),
        source_published_at_utc=published,
        projected_at_utc=published,
        payload=configuration,
    )


def test_provider_returns_none_without_projected_tool() -> None:
    provider = ToolConfigurationKpiDestinationCatalogProvider(
        projection=ProjectionMemory(),
        source_key=SourceKey('tools'),
    )

    assert provider.load() is None


def test_provider_preserves_projection_target_and_catalog() -> None:
    record = projection(ToolConfiguration.from_document(tool_document()))
    provider = ToolConfigurationKpiDestinationCatalogProvider(
        projection=ProjectionMemory(record),
        source_key=SourceKey('tools'),
    )

    snapshot = provider.load()

    assert snapshot is not None
    assert snapshot.projection_target == record.target
    assert tuple(destination.key for destination in snapshot.catalog.destinations) == (
        'global_indicators',
        'time_status',
        'crusher',
    )
    assert 'primary' not in snapshot.catalog.keys


def test_projected_tool_without_structure_is_invalid_not_absent() -> None:
    document = tool_document()
    document['structure'] = None
    record = projection(ToolConfiguration.from_document(document))
    provider = ToolConfigurationKpiDestinationCatalogProvider(
        projection=ProjectionMemory(record),
        source_key=SourceKey('tools'),
    )

    with pytest.raises(KpiRegistryValidationError, match='does not contain structure'):
        provider.load()
