from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ada.web.application.generic.bootstrap import create_operational_application_runtime
from ada.web.application.generic.settings import AdaGenericSettings
from ada.web.kpis.collector import (
    ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY,
    ADA_KPI_COLLECTOR_SERVICE_KEY,
    AdaKpiCollector,
    AdaKpiCollectorPollingRuntime,
)
from ada.web.tools.configuration import ToolConfiguration
from ada.web.tools.persistence import compose_tool_persistence
from atlanticus.connectivity.storage import StorageClient
from atlanticus.web.models import WebApplicationRuntime
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId


def _local_settings(tmp_path: Path, *, with_kpi_delivery: bool = False) -> AdaGenericSettings:
    values = {
        'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
        'ADA_TOOL_SOURCE_PROVIDER': 'local',
        'ADA_TOOL_PROJECTION_PROVIDER': 'local',
        'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path),
    }
    if with_kpi_delivery:
        values.update(
            {
                'COSMOS_CONSUMPTION_ENDPOINT': 'https://consumption.example.test',
                'COSMOS_CONSUMPTION_KEY': 'consumption-key',
                'COSMOS_CONSUMPTION_DATABASE_NAME': 'consumption',
            }
        )
    return AdaGenericSettings.from_mapping(values)


def _blob_local_settings(tmp_path: Path) -> AdaGenericSettings:
    return AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
            'ADA_TOOL_SOURCE_PROVIDER': 'blob',
            'ADA_TOOL_PROJECTION_PROVIDER': 'local',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path),
            'ADA_TOOL_SOURCE_BLOB_CONTAINER_NAME': 'configuration',
            'ADA_TOOL_SOURCE_BLOB_CONNECTION_STRING': 'UseDevelopmentStorage=true',
        }
    )


def _configuration() -> ToolConfiguration:
    return ToolConfiguration.from_document(
        {
            'tool_key': 'integrated_operations',
            'display_name': 'Operaciones Integradas',
            'kind': 'integrated_operations',
            'source_consumption': {
                'tool_key': 'integrated_operations',
                'source_keys': ['pi'],
            },
            'source_operational_participation': {
                'tool_key': 'integrated_operations',
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
                'tool_key': 'integrated_operations',
                'kind': 'integrated_operations',
                'operational_scope': None,
                'components': [
                    {
                        'key': 'mine',
                        'display_name': 'Mina',
                        'scope': 'mine',
                        'layout_role': None,
                        'subcomponents': [
                            {
                                'key': 'mine_phase',
                                'display_name': 'Fase Mina',
                                'linked_component_keys': [],
                            }
                        ],
                    },
                    {
                        'key': 'plant',
                        'display_name': 'Planta',
                        'scope': 'plant',
                        'layout_role': None,
                        'subcomponents': [
                            {
                                'key': 'plant_phase',
                                'display_name': 'Fase Planta',
                                'linked_component_keys': [],
                            }
                        ],
                    },
                ],
            },
        }
    )


def _projection() -> ProjectionRecord[ToolConfiguration]:
    timestamp = datetime(2026, 9, 21, 4, tzinfo=UTC)
    return ProjectionRecord(
        source_key=SourceKey('tools'),
        source_release_id=SourceReleaseId('tool-release-current'),
        source_published_at_utc=timestamp,
        projected_at_utc=timestamp,
        payload=_configuration(),
    )


def _persist_projection(settings: AdaGenericSettings) -> None:
    storage_settings = settings.storage_settings()
    storage_client = (
        StorageClient(settings=storage_settings) if storage_settings is not None else None
    )
    try:
        composition = compose_tool_persistence(
            settings=settings.tool_persistence_settings(),
            storage_client=storage_client,
        )
        composition.projection.replace_active(_projection())
    finally:
        if storage_client is not None:
            storage_client.close()


def test_empty_local_persistence_keeps_base_web_runtime_available(tmp_path: Path) -> None:
    runtime = create_operational_application_runtime(settings=_local_settings(tmp_path))

    assert isinstance(runtime, WebApplicationRuntime)
    assert not runtime.services.contains(ADA_KPI_COLLECTOR_SERVICE_KEY)


def test_active_projection_without_kpi_connection_keeps_web_available(
    tmp_path: Path,
    caplog,
) -> None:
    settings = _local_settings(tmp_path)
    _persist_projection(settings)
    caplog.set_level('INFO', logger='ada.web.application.generic.bootstrap')

    runtime = create_operational_application_runtime(settings=settings)

    assert isinstance(runtime, WebApplicationRuntime)
    assert not runtime.services.contains(ADA_KPI_COLLECTOR_SERVICE_KEY)
    assert 'KPI Collector is not configured' in caplog.text


def test_ready_projection_with_kpi_connection_attaches_lazy_collector(tmp_path: Path) -> None:
    settings = _local_settings(tmp_path, with_kpi_delivery=True)
    _persist_projection(settings)

    runtime = create_operational_application_runtime(settings=settings)

    collector = runtime.services.require(ADA_KPI_COLLECTOR_SERVICE_KEY, AdaKpiCollector)
    polling_runtime = runtime.services.require(
        ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY,
        AdaKpiCollectorPollingRuntime,
    )
    assert isinstance(runtime, WebApplicationRuntime)
    assert collector.tool_projection_revision == 'tool-release-current'
    assert tuple(component.key for component in collector.structure.components) == ('mine', 'plant')
    assert polling_runtime.is_running is False


def test_blob_source_is_not_read_when_local_active_projection_exists(tmp_path: Path) -> None:
    settings = _blob_local_settings(tmp_path)
    _persist_projection(settings)

    runtime = create_operational_application_runtime(settings=settings)

    assert isinstance(runtime, WebApplicationRuntime)


def test_corrupt_projection_keeps_base_web_runtime_available_and_logs_invalid(
    tmp_path: Path,
    caplog,
) -> None:
    settings = _local_settings(tmp_path)
    _persist_projection(settings)
    projection_file = next(
        settings.tool_persistence_settings()
        .namespace.local_projection_root(tmp_path)
        .glob('tool_projection_*.json')
    )
    projection_file.write_text('{"document_type":"wrong"}', encoding='utf-8')
    caplog.set_level('ERROR', logger='ada.web.application.generic.operational_tool')

    runtime = create_operational_application_runtime(settings=settings)

    assert isinstance(runtime, WebApplicationRuntime)
    assert not runtime.services.contains(ADA_KPI_COLLECTOR_SERVICE_KEY)
    assert 'Operational Tool configuration is invalid' in caplog.text
