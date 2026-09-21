from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ada.web.application.generic import operational_tool
from ada.web.application.generic.operational_collector import create_operational_kpi_collector
from ada.web.application.generic.operational_tool import (
    create_definition_from_tool_resolution,
    resolve_operational_tool_projection,
)
from ada.web.kpis.collector import CosmosKpiDeliveryReaderSettings
from ada.web.storage.namespace import AdaStorageNamespace
from ada.web.tools.configuration import ToolConfiguration
from ada.web.tools.persistence import (
    ToolPersistenceSettings,
    ToolProjectionProvider,
    ToolProjectionResolution,
    ToolProjectionResolutionState,
    ToolSourceProvider,
    compose_tool_persistence,
)
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


def _configuration(*, operational: bool = True) -> ToolConfiguration:
    participation = (
        {
            'tool_key': 'integrated_operations',
            'control_sources': [
                {
                    'source_key': 'pi',
                    'pre_degrading_after_seconds': 200,
                    'degrading_after_seconds': 300,
                }
            ],
            'additional_observation_source_keys': [],
        }
        if operational
        else {
            'tool_key': 'integrated_operations',
            'control_sources': [],
            'additional_observation_source_keys': ['pi'],
        }
    )
    return ToolConfiguration.from_document(
        {
            'tool_key': 'integrated_operations',
            'display_name': 'Operaciones Integradas',
            'kind': 'integrated_operations',
            'source_consumption': {
                'tool_key': 'integrated_operations',
                'source_keys': ['pi'],
            },
            'source_operational_participation': participation,
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


def _projection(*, operational: bool = True) -> ProjectionRecord[ToolConfiguration]:
    timestamp = datetime(2026, 9, 21, 4, tzinfo=UTC)
    return ProjectionRecord(
        source_key=SourceKey('tools'),
        source_release_id=SourceReleaseId('tool-release-current'),
        source_published_at_utc=timestamp,
        projected_at_utc=timestamp,
        payload=_configuration(operational=operational),
    )


def _local_composition(tmp_path: Path):
    return compose_tool_persistence(
        settings=ToolPersistenceSettings(
            namespace=AdaStorageNamespace(
                application_namespace='conciencia_situacional',
                tool_namespace='operaciones_integradas',
            ),
            source_provider=ToolSourceProvider.LOCAL,
            projection_provider=ToolProjectionProvider.LOCAL,
            local_base_root=tmp_path,
        )
    )


def test_operational_resolution_reads_active_durable_projection(tmp_path: Path) -> None:
    composition = _local_composition(tmp_path)
    composition.projection.replace_active(_projection())

    resolution = resolve_operational_tool_projection(composition)

    assert resolution.state is ToolProjectionResolutionState.READY
    assert resolution.projection == _projection()


def test_ada_operational_validation_turns_generic_ready_projection_into_invalid(
    tmp_path: Path,
) -> None:
    composition = _local_composition(tmp_path)
    composition.projection.replace_active(_projection(operational=False))

    resolution = resolve_operational_tool_projection(composition)

    assert resolution.state is ToolProjectionResolutionState.INVALID
    assert resolution.error_type == 'ToolConfigurationValidationError'
    assert resolution.message == (
        'ADA operational Tool Configuration requires PI as a CONTROL source'
    )


def test_ready_resolution_threads_projection_into_application_definition(monkeypatch) -> None:
    captured: dict[str, object] = {}
    expected_definition = object()

    def create_definition(**kwargs):
        captured.update(kwargs)
        return expected_definition

    monkeypatch.setattr(operational_tool, 'create_application_definition', create_definition)

    definition = create_definition_from_tool_resolution(
        ToolProjectionResolution(
            state=ToolProjectionResolutionState.READY,
            projection=_projection(),
        )
    )

    configuration = _configuration()
    assert definition is expected_definition
    assert captured == {
        'tool_display_name': configuration.display_name,
        'branding_configuration': configuration.branding,
        'source_consumption': configuration.source_consumption,
        'source_operational_participation': configuration.source_operational_participation,
    }


def test_unconfigured_resolution_keeps_base_definition(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    expected_definition = object()

    def create_definition(**kwargs):
        calls.append(kwargs)
        return expected_definition

    monkeypatch.setattr(operational_tool, 'create_application_definition', create_definition)

    definition = create_definition_from_tool_resolution(
        ToolProjectionResolution(state=ToolProjectionResolutionState.UNCONFIGURED)
    )

    assert definition is expected_definition
    assert calls == [{}]


def test_unavailable_resolution_keeps_base_definition_and_logs_diagnostic(
    monkeypatch,
    caplog,
) -> None:
    expected_definition = object()
    monkeypatch.setattr(
        operational_tool,
        'create_application_definition',
        lambda **kwargs: expected_definition,
    )
    caplog.set_level('WARNING', logger='ada.web.application.generic.operational_tool')

    definition = create_definition_from_tool_resolution(
        ToolProjectionResolution(
            state=ToolProjectionResolutionState.UNAVAILABLE,
            error_type='CosmosOperationError',
            message='Cosmos unavailable',
        )
    )

    assert definition is expected_definition
    assert 'Operational Tool is unavailable' in caplog.text
    assert 'CosmosOperationError' in caplog.text


def test_invalid_resolution_keeps_base_definition_and_logs_diagnostic(
    monkeypatch,
    caplog,
) -> None:
    expected_definition = object()
    monkeypatch.setattr(
        operational_tool,
        'create_application_definition',
        lambda **kwargs: expected_definition,
    )
    caplog.set_level('ERROR', logger='ada.web.application.generic.operational_tool')

    definition = create_definition_from_tool_resolution(
        ToolProjectionResolution(
            state=ToolProjectionResolutionState.INVALID,
            error_type='ToolConfigurationProjectionError',
            message='Projection is invalid',
        )
    )

    assert definition is expected_definition
    assert 'Operational Tool configuration is invalid' in caplog.text
    assert 'ToolConfigurationProjectionError' in caplog.text


def test_collector_factory_preserves_tool_revision_and_reader_containers() -> None:
    projection = _projection()
    client = CosmosClientStub()

    collector = create_operational_kpi_collector(
        tool_projection=projection,
        cosmos_client=client,
        reader_settings=CosmosKpiDeliveryReaderSettings(
            latest_container_name='latest-custom',
            timeseries_container_name='timeseries-custom',
        ),
    )
    latest_result = collector.refresh_latest()
    timeseries_result = collector.refresh_timeseries()

    assert collector.tool_projection_revision == 'tool-release-current'
    assert collector.structure is projection.payload.structure
    assert latest_result.status.value == 'missing'
    assert timeseries_result.status.value == 'missing'
    assert client.calls[0][0] == 'latest-custom'
    assert client.calls[1][0] == 'timeseries-custom'
