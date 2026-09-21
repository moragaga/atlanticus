from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ada.web.application.generic import operational_tool
from ada.web.application.generic.operational_collector import create_operational_kpi_collector
from ada.web.application.generic.operational_tool import (
    create_runtime_from_tool_resolution,
    resolve_operational_tool_projection,
)
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
    def find_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
        include_metadata: bool = False,
    ) -> dict[str, object] | None:
        del container_name, item_id, partition_key, include_metadata
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


def test_ready_resolution_threads_projection_into_existing_runtime(monkeypatch) -> None:
    captured: dict[str, object] = {}
    expected_runtime = object()

    def create_runtime(**kwargs):
        captured.update(kwargs)
        return expected_runtime

    monkeypatch.setattr(operational_tool, 'create_application_runtime', create_runtime)

    runtime = create_runtime_from_tool_resolution(
        ToolProjectionResolution(
            state=ToolProjectionResolutionState.READY,
            projection=_projection(),
        )
    )

    configuration = _configuration()
    assert runtime is expected_runtime
    assert captured == {
        'tool_display_name': configuration.display_name,
        'branding_configuration': configuration.branding,
        'source_consumption': configuration.source_consumption,
        'source_operational_participation': configuration.source_operational_participation,
    }


def test_unconfigured_resolution_keeps_base_runtime(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    expected_runtime = object()

    def create_runtime(**kwargs):
        calls.append(kwargs)
        return expected_runtime

    monkeypatch.setattr(operational_tool, 'create_application_runtime', create_runtime)

    runtime = create_runtime_from_tool_resolution(
        ToolProjectionResolution(state=ToolProjectionResolutionState.UNCONFIGURED)
    )

    assert runtime is expected_runtime
    assert calls == [{}]


def test_unavailable_resolution_keeps_base_runtime_and_logs_diagnostic(
    monkeypatch,
    caplog,
) -> None:
    expected_runtime = object()
    monkeypatch.setattr(
        operational_tool,
        'create_application_runtime',
        lambda **kwargs: expected_runtime,
    )
    caplog.set_level('WARNING', logger='ada.web.application.generic.operational_tool')

    runtime = create_runtime_from_tool_resolution(
        ToolProjectionResolution(
            state=ToolProjectionResolutionState.UNAVAILABLE,
            error_type='CosmosOperationError',
            message='Cosmos unavailable',
        )
    )

    assert runtime is expected_runtime
    assert 'Operational Tool is unavailable' in caplog.text
    assert 'CosmosOperationError' in caplog.text


def test_invalid_resolution_keeps_base_runtime_and_logs_diagnostic(
    monkeypatch,
    caplog,
) -> None:
    expected_runtime = object()
    monkeypatch.setattr(
        operational_tool,
        'create_application_runtime',
        lambda **kwargs: expected_runtime,
    )
    caplog.set_level('ERROR', logger='ada.web.application.generic.operational_tool')

    runtime = create_runtime_from_tool_resolution(
        ToolProjectionResolution(
            state=ToolProjectionResolutionState.INVALID,
            error_type='ToolConfigurationProjectionError',
            message='Projection is invalid',
        )
    )

    assert runtime is expected_runtime
    assert 'Operational Tool configuration is invalid' in caplog.text
    assert 'ToolConfigurationProjectionError' in caplog.text


def test_collector_factory_preserves_developer_owned_render_boundary() -> None:
    projection = _projection()

    collector = create_operational_kpi_collector(
        tool_projection=projection,
        cosmos_client=CosmosClientStub(),
    )

    assert collector.tool_projection_revision == 'tool-release-current'
    assert collector.structure is projection.payload.structure
    assert collector.operational_render_binding.structure is projection.payload.structure
    assert tuple(
        binding.component.key for binding in collector.operational_render_binding.components
    ) == ('mine', 'plant')
