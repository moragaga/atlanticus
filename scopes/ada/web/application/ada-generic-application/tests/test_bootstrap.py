from __future__ import annotations

import json
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
from atlanticus.web.models import WebApplicationRuntime
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId


def _local_settings(tmp_path: Path, *, with_kpi_delivery: bool = False) -> AdaGenericSettings:
    values = {
        'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
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
    composition = compose_tool_persistence(settings=settings.tool_persistence_settings())
    composition.projection.replace_active(_projection())


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
    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)
    assert response.status_code == 200
    assert 'ada-alarm-baseline-surface' in payload
    assert 'data-ada-alarm-baseline-tool-key' in payload
    assert 'integrated_operations' in payload
    assert 'data-ada-component-key' in payload


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
