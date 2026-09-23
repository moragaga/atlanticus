from datetime import UTC, datetime

from ada_command_center.domain.alarms import AlarmConfigurationSnapshot
from ada_command_center.domain.tools import ToolDependencyManifest
from ada_command_center.web.alarms.configuration import (
    AlarmConfigurationProjectionBuilder,
    AlarmConfigurationSourceCodec,
    create_alarm_configuration_projection_service,
)
from atlanticus.web.projection.models import (
    ProjectionAlignment,
    ProjectionRecord,
    ProjectionTarget,
)
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)
from atlanticus.web.source.store import SourceStore

from .helpers import configuration


def _alarm_snapshot() -> AlarmConfigurationSnapshot:
    return AlarmConfigurationSnapshot(
        configuration=configuration(),
        tool_dependencies=ToolDependencyManifest(
            confirmed_tool_catalog_revision='tools-r2',
            tools=(),
        ),
    )


class SourceStoreStub(SourceStore):
    def __init__(self) -> None:
        self.source_key = SourceKey('ada-command-center-alarms')
        self.release_ref = SourceReleaseRef(
            release_id=SourceReleaseId('release-1'),
            published_at_utc=datetime(2026, 9, 21, 12, 0, tzinfo=UTC),
        )
        self.resource = AlarmConfigurationSourceCodec().encode(
            snapshot=_alarm_snapshot(),
            published_by='manager-user',
        )
        self.metadata = SourceReleaseMetadata(
            schema_version=1,
            source_key=self.source_key,
            release_ref=self.release_ref,
            content_hash=Digest('sha256', 'abc'),
            resources=(),
        )
        self.snapshot = SourceSnapshot(
            source_key=self.source_key,
            current=SourceReleaseSummary(
                release_ref=self.release_ref,
                content_hash=self.metadata.content_hash,
            ),
            concurrency_token=ConcurrencyToken('etag-1'),
        )

    def get_current(self, source_key):
        assert source_key == self.source_key
        return self.snapshot

    def read_release(self, source_key, release_ref):
        assert source_key == self.source_key
        assert release_ref == self.release_ref
        return self.metadata, (self.resource,)

    def publish(self, request):
        raise AssertionError(request)

    def query_history(self, query):
        raise AssertionError(query)

    def verify_release(self, source_key, release_ref):
        raise AssertionError((source_key, release_ref))


class ProjectionStoreStub(ProjectionStore):
    def __init__(self) -> None:
        self.active = None

    def get_active(self, source_key):
        if self.active is None:
            return None
        assert self.active.source_key == source_key
        return self.active

    def replace_active(self, projection):
        self.active = projection
        return projection


def test_alarm_configuration_projection_builder_preserves_versioned_snapshot() -> None:
    source = SourceStoreStub()
    builder = AlarmConfigurationProjectionBuilder()

    target = ProjectionTarget(
        source_key=source.source_key,
        source_release=source.release_ref,
    )

    projected = builder.build(
        target=target,
        release=source.metadata,
        resources=(source.resource,),
    )

    assert projected == _alarm_snapshot()


def test_alarm_configuration_projection_selects_exact_source_target_without_dependencies() -> None:
    source = SourceStoreStub()
    service = create_alarm_configuration_projection_service(
        source=source,
        projection=ProjectionStoreStub(),
    )

    target = service.select_current_target(source.source_key)

    assert target is not None
    assert target.source_key == source.source_key
    assert target.source_release == source.release_ref
    assert target.dependencies == ()


def test_alarm_configuration_projection_preserves_alarm_and_tool_revisions() -> None:
    source = SourceStoreStub()
    projection = ProjectionStoreStub()
    service = create_alarm_configuration_projection_service(
        source=source,
        projection=projection,
    )
    target = service.select_current_target(source.source_key)
    assert target is not None

    result = service.project(target)
    status = service.get_status(source.source_key)

    assert isinstance(result.projection, ProjectionRecord)
    assert result.projection.source_release_id.value == 'release-1'
    assert result.projection.payload.confirmed_tool_catalog_revision == 'tools-r2'
    assert result.projection.payload.tool_dependencies.revision == 'tools-r2'
    assert result.projection.payload.configuration == configuration()
    assert result.projection.target == target
    assert status.alignment is ProjectionAlignment.CURRENT
