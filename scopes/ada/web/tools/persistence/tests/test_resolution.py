from datetime import UTC, datetime
from pathlib import Path

from ada.web.storage.namespace import AdaStorageNamespace
from ada.web.tools.configuration import (
    ToolConfiguration,
    create_tool_projection_service,
)
from ada.web.tools.persistence import (
    ToolPersistenceComposition,
    ToolPersistenceSettings,
    ToolProjectionProvider,
    ToolProjectionResolutionState,
    ToolSourceProvider,
    compose_tool_persistence,
    project_current_tool_source,
    resolve_active_tool_projection,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.errors import SourceUnavailableError
from atlanticus.web.source.models import (
    HistoryPage,
    HistoryQuery,
    IntegrityResult,
    PublishRequest,
    PublishResult,
    SourceKey,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceResource,
    SourceSnapshot,
)
from atlanticus.web.source.store import SourceStore


def _namespace() -> AdaStorageNamespace:
    return AdaStorageNamespace(
        application_namespace='conciencia_situacional',
        tool_namespace='operaciones_integradas',
    )


def _settings(tmp_path: Path) -> ToolPersistenceSettings:
    return ToolPersistenceSettings(
        namespace=_namespace(),
        source_provider=ToolSourceProvider.LOCAL,
        projection_provider=ToolProjectionProvider.LOCAL,
        local_base_root=tmp_path,
    )


def _configuration() -> ToolConfiguration:
    return ToolConfiguration.from_document(
        {
            'tool_key': 'operaciones_integradas',
            'display_name': 'Operaciones Integradas',
            'kind': 'process',
            'source_consumption': {
                'tool_key': 'operaciones_integradas',
                'source_keys': ['pi'],
            },
            'source_operational_participation': {
                'tool_key': 'operaciones_integradas',
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
                'tool_key': 'operaciones_integradas',
                'kind': 'process',
                'operational_scope': 'mine',
                'components': [
                    {
                        'key': 'center',
                        'display_name': 'Centro',
                        'layout_role': 'center',
                        'subcomponents': [
                            {
                                'key': 'primary',
                                'display_name': 'Principal',
                                'linked_component_keys': [],
                            }
                        ],
                    }
                ],
            },
        }
    )


def _projection() -> ProjectionRecord[ToolConfiguration]:
    timestamp = datetime(2026, 9, 21, 3, tzinfo=UTC)
    return ProjectionRecord(
        source_key=SourceKey('tools'),
        source_release_id=SourceReleaseId('release-1'),
        source_published_at_utc=timestamp,
        projected_at_utc=timestamp,
        payload=_configuration(),
    )


def test_empty_persistence_is_unconfigured_and_does_not_fail_startup(
    tmp_path: Path,
) -> None:
    composition = compose_tool_persistence(settings=_settings(tmp_path))

    active = resolve_active_tool_projection(composition)
    projected = project_current_tool_source(composition)

    assert active.state is ToolProjectionResolutionState.UNCONFIGURED
    assert projected.state is ToolProjectionResolutionState.UNCONFIGURED


class _UnavailableSourceStore(SourceStore):
    def get_current(self, source_key: SourceKey) -> SourceSnapshot:
        raise SourceUnavailableError('source is unavailable')

    def read_release(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ) -> tuple[SourceReleaseMetadata, tuple[SourceResource, ...]]:
        raise NotImplementedError

    def publish(self, request: PublishRequest) -> PublishResult:
        raise NotImplementedError

    def query_history(self, query: HistoryQuery) -> HistoryPage:
        raise NotImplementedError

    def verify_release(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ) -> IntegrityResult:
        raise NotImplementedError


def _with_source(
    composition: ToolPersistenceComposition,
    source: SourceStore,
) -> ToolPersistenceComposition:
    return ToolPersistenceComposition(
        settings=composition.settings,
        source=source,
        projection=composition.projection,
        projection_service=create_tool_projection_service(
            source=source,
            projection=composition.projection,
        ),
    )


def test_runtime_can_use_active_projection_without_reading_source(
    tmp_path: Path,
) -> None:
    composition = compose_tool_persistence(settings=_settings(tmp_path))
    composition.projection.replace_active(_projection())
    unavailable = _with_source(composition, _UnavailableSourceStore())

    result = resolve_active_tool_projection(unavailable)

    assert result.state is ToolProjectionResolutionState.READY
    assert result.projection == _projection()


def test_source_unavailability_is_state_not_exception(tmp_path: Path) -> None:
    composition = _with_source(
        compose_tool_persistence(settings=_settings(tmp_path)),
        _UnavailableSourceStore(),
    )

    result = project_current_tool_source(composition)

    assert result.state is ToolProjectionResolutionState.UNAVAILABLE
    assert result.projection is None
    assert result.error_type == 'SourceUnavailableError'


def test_corrupt_local_projection_is_invalid_not_startup_failure(
    tmp_path: Path,
) -> None:
    composition = compose_tool_persistence(settings=_settings(tmp_path))
    composition.projection.replace_active(_projection())
    projection_file = next(
        _settings(tmp_path).namespace.local_projection_root(tmp_path).glob('tool_projection_*.json')
    )
    projection_file.write_text('{"document_type":"wrong"}', encoding='utf-8')

    result = resolve_active_tool_projection(composition)

    assert result.state is ToolProjectionResolutionState.INVALID
    assert result.projection is None
    assert result.error_type is not None
