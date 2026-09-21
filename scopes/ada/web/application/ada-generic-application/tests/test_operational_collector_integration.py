from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.operational_collector import attach_operational_kpi_collector
from ada.web.kpis.collector import (
    ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY,
    ADA_KPI_COLLECTOR_SERVICE_KEY,
    DEFAULT_KPI_LATEST_DELIVERY_CONTAINER,
    DEFAULT_KPI_TIMESERIES_DELIVERY_CONTAINER,
    AdaKpiCollector,
    AdaKpiCollectorPollingRuntime,
)
from ada.web.tools.configuration import ToolConfiguration
from atlanticus.web.application import create_web_application
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId


class CosmosClientStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

    def find_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
        include_metadata: bool = False,
    ) -> dict[str, object] | None:
        del include_metadata
        self.calls.append((container_name, item_id, partition_key))
        return None


def _tool_configuration(*, with_structure: bool = True) -> ToolConfiguration:
    document: dict[str, object] = {
        'tool_key': 'process',
        'display_name': 'Proceso',
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
        'structure': (
            {
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
            }
            if with_structure
            else None
        ),
    }
    return ToolConfiguration.from_document(document)


def _tool_projection(
    *,
    release_id: str = 'tool-release-r17',
    configuration: ToolConfiguration | None = None,
) -> ProjectionRecord[ToolConfiguration]:
    return ProjectionRecord(
        source_key=SourceKey('tools'),
        source_release_id=SourceReleaseId(release_id),
        source_published_at_utc=datetime(2026, 9, 20, 20, 0, tzinfo=UTC),
        projected_at_utc=datetime(2026, 9, 20, 20, 1, tzinfo=UTC),
        payload=configuration or _tool_configuration(),
    )


def test_operational_attachment_builds_collector_from_exact_tool_projection() -> None:
    projection = _tool_projection(release_id='tool-release-exact')
    cosmos = CosmosClientStub()
    definition = attach_operational_kpi_collector(
        create_application_definition(),
        tool_projection=projection,
        cosmos_client=cosmos,
    )
    runtime = create_web_application(definition)

    collector = runtime.services.require(ADA_KPI_COLLECTOR_SERVICE_KEY, AdaKpiCollector)
    polling_runtime = runtime.services.require(
        ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY,
        AdaKpiCollectorPollingRuntime,
    )

    assert collector.structure is projection.payload.structure
    assert collector.tool_projection_revision == 'tool-release-exact'
    assert tuple(component.key for component in collector.structure.components) == ('crusher',)

    cycle = polling_runtime.poll_due(now=0.0)

    assert cycle.latest is not None
    assert cycle.timeseries is not None
    assert cosmos.calls == [
        (DEFAULT_KPI_LATEST_DELIVERY_CONTAINER, 'latest', 'kpis'),
        (DEFAULT_KPI_TIMESERIES_DELIVERY_CONTAINER, 'timeseries', 'kpis'),
    ]


def test_operational_attachment_rejects_non_tool_projection_payload() -> None:
    invalid_projection = ProjectionRecord(
        source_key=SourceKey('tools'),
        source_release_id=SourceReleaseId('tool-release-r1'),
        source_published_at_utc=datetime(2026, 9, 20, 20, 0, tzinfo=UTC),
        projected_at_utc=datetime(2026, 9, 20, 20, 1, tzinfo=UTC),
        payload=object(),
    )

    with pytest.raises(TypeError, match='payload must be ToolConfiguration'):
        attach_operational_kpi_collector(
            create_application_definition(),
            tool_projection=invalid_projection,
            cosmos_client=CosmosClientStub(),
        )


def test_operational_attachment_requires_operational_tool_structure() -> None:
    projection = _tool_projection(configuration=_tool_configuration(with_structure=False))

    with pytest.raises(ValueError, match='requires Tool Structure'):
        attach_operational_kpi_collector(
            create_application_definition(),
            tool_projection=projection,
            cosmos_client=CosmosClientStub(),
        )


def test_operational_attachment_rejects_cosmos_client_without_find_item() -> None:
    with pytest.raises(TypeError, match='find_item'):
        attach_operational_kpi_collector(
            create_application_definition(),
            tool_projection=_tool_projection(),
            cosmos_client=object(),
        )
