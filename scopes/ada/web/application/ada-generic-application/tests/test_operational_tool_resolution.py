from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.web.application.generic.operational_collector import create_operational_kpi_collector
from ada.web.application.generic.operational_tool import resolve_current_tool_projection
from ada.web.tools.configuration import ToolConfiguration, ToolSourceCodec
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    HistoryPage,
    HistoryQuery,
    IntegrityResult,
    PublishRequest,
    PublishResult,
    SourceKey,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)
from atlanticus.web.source.store import SourceStore


class SourceStoreStub(SourceStore):
    def __init__(
        self,
        *,
        source_key: SourceKey,
        release_ref: SourceReleaseRef | None,
        configuration: ToolConfiguration | None = None,
    ) -> None:
        self._source_key = source_key
        self._release_ref = release_ref
        self._configuration = configuration

    def get_current(self, source_key: SourceKey) -> SourceSnapshot:
        assert source_key == self._source_key
        if self._release_ref is None:
            return SourceSnapshot(source_key, None, None)
        return SourceSnapshot(
            source_key,
            SourceReleaseSummary(self._release_ref, Digest('sha256', 'source-hash')),
            ConcurrencyToken('source-token'),
        )

    def read_release(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ):
        assert source_key == self._source_key
        assert release_ref == self._release_ref
        assert self._configuration is not None
        resource = ToolSourceCodec().encode(
            configuration=self._configuration,
            published_by='test-user',
        )
        metadata = SourceReleaseMetadata(
            schema_version=1,
            source_key=source_key,
            release_ref=release_ref,
            content_hash=Digest('sha256', 'source-hash'),
            resources=(),
        )
        return metadata, (resource,)

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


def _release_ref() -> SourceReleaseRef:
    return SourceReleaseRef(
        release_id=SourceReleaseId('tool-release-current'),
        published_at_utc=datetime(2026, 9, 20, 20, 0, tzinfo=UTC),
    )


def test_current_tool_projection_uses_exact_source_release_and_configuration() -> None:
    source = SourceStoreStub(
        source_key=SourceKey('tools'),
        release_ref=_release_ref(),
        configuration=_configuration(),
    )

    projection = resolve_current_tool_projection(source=source)

    assert projection.source_key == SourceKey('tools')
    assert projection.source_release_id == SourceReleaseId('tool-release-current')
    assert projection.payload == _configuration()
    assert projection.payload.structure is not None
    assert tuple(component.key for component in projection.payload.structure.components) == (
        'mine',
        'plant',
    )


def test_current_tool_projection_requires_published_source_release() -> None:
    source = SourceStoreStub(
        source_key=SourceKey('tools'),
        release_ref=None,
    )

    with pytest.raises(RuntimeError, match='has no current release'):
        resolve_current_tool_projection(source=source)


def test_collector_factory_preserves_developer_owned_render_boundary() -> None:
    projection = resolve_current_tool_projection(
        source=SourceStoreStub(
            source_key=SourceKey('tools'),
            release_ref=_release_ref(),
            configuration=_configuration(),
        )
    )

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
