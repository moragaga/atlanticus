from __future__ import annotations

import json
from datetime import UTC, datetime

from ada.web.alarms.collector import (
    ADA_ALARM_COLLECTOR_RUNTIME_SERVICE_KEY,
    ADA_ALARM_COLLECTOR_SERVICE_KEY,
    AdaAlarmCollector,
    AdaAlarmCollectorPollingRuntime,
)
from ada.web.application.generic import bootstrap
from ada.web.application.generic.settings import AdaGenericSettings
from ada.web.kpis.collector import (
    ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY,
    AdaKpiCollectorPollingRuntime,
)
from ada.web.tools.configuration import ToolConfiguration
from ada.web.tools.persistence import ToolProjectionResolution, ToolProjectionResolutionState
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId


def _ready_tool_projection() -> ProjectionRecord[ToolConfiguration]:
    configuration = ToolConfiguration.from_document(
        {
            'tool_key': 'process',
            'display_name': 'Proceso',
            'kind': 'process',
            'source_consumption': {'tool_key': 'process', 'source_keys': ['pi']},
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
                'center_component_key': 'crusher',
                'components': [
                    {
                        'key': 'crusher',
                        'display_name': 'Chancado',
                        'scope': None,
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
    )
    timestamp = datetime(2026, 9, 20, 20, tzinfo=UTC)
    return ProjectionRecord(
        source_key=SourceKey('tools'),
        source_release_id=SourceReleaseId('test-release'),
        source_published_at_utc=timestamp,
        projected_at_utc=timestamp,
        payload=configuration,
    )


def test_primary_cosmos_drives_both_collectors_without_documents(monkeypatch) -> None:
    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_PERSISTENCE_MODE': 'durable',
            'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
            'ADA_STORAGE_CONNECTION_STRING': 'UseDevelopmentStorage=true',
            'ADA_COSMOS_ENDPOINT': 'https://cosmos.example.test',
            'ADA_COSMOS_KEY': 'cosmos-key',
            'ADA_COSMOS_DATABASE_NAME': 'configuration',
        }
    )

    class EmptyCosmos:
        def __init__(self, *, settings):
            self.settings = settings
            self.calls = []

        def find_item(self, *, container_name, item_id, partition_key, include_metadata=False):
            self.calls.append((container_name, item_id, partition_key))
            return None

    clients = []

    def create_client(*, settings):
        client = EmptyCosmos(settings=settings)
        clients.append(client)
        return client

    monkeypatch.setattr(
        bootstrap,
        '_resolve_tool_projection',
        lambda _settings: ToolProjectionResolution(
            state=ToolProjectionResolutionState.READY,
            projection=_ready_tool_projection(),
        ),
    )
    monkeypatch.setattr(bootstrap, 'CosmosClient', create_client)

    runtime = bootstrap.create_operational_application_runtime(settings=settings)
    alarm = runtime.services.require(ADA_ALARM_COLLECTOR_SERVICE_KEY, AdaAlarmCollector)
    alarm_polling = runtime.services.require(
        ADA_ALARM_COLLECTOR_RUNTIME_SERVICE_KEY, AdaAlarmCollectorPollingRuntime,
    )
    kpi_polling = runtime.services.require(
        ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY, AdaKpiCollectorPollingRuntime,
    )

    assert len(clients) == 1
    assert clients[0].settings.database_name == 'configuration'
    assert alarm_polling.poll_due(now=0.0).error is None
    kpi_result = kpi_polling.poll_due(now=0.0)
    assert kpi_result.latest is not None
    assert kpi_result.timeseries is not None
    assert alarm.snapshot.availability.value == 'missing'
    assert ('alarm-live-projection', 'alarm-live:process', 'process') in clients[0].calls
    assert len(clients[0].calls) == 3

    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)
    assert response.status_code == 200
    assert 'ada-alarm-collector-refresh' in payload
    assert 'ada-alarm-live-store' in payload
