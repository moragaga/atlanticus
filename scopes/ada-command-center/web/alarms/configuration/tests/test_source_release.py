from datetime import UTC, datetime

from ada_command_center.domain.alarms import AlarmConfigurationSnapshot
from ada_command_center.domain.tools import ToolDependencyManifest
from ada_command_center.web.alarms.configuration import (
    ALARM_CONFIGURATION_SOURCE_RESOURCE_PATH,
    ALARM_CONFIGURATION_SOURCE_SCHEMA_VERSION,
    AlarmConfigurationSourceCodec,
    AlarmConfigurationSourceService,
)
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    HistoryPage,
    PublishResult,
    SourceKey,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)

from .helpers import configuration


def _release_ref(value: str = 'release-1') -> SourceReleaseRef:
    return SourceReleaseRef(
        release_id=SourceReleaseId(value),
        published_at_utc=datetime(2026, 9, 21, 12, 0, tzinfo=UTC),
    )


def _snapshot(revision: str = 'tools-r2') -> AlarmConfigurationSnapshot:
    return AlarmConfigurationSnapshot(
        configuration=configuration(),
        tool_dependencies=ToolDependencyManifest(
            confirmed_tool_catalog_revision=revision,
            tools=(),
        ),
    )


def test_alarm_configuration_source_codec_round_trips_versioned_snapshot() -> None:
    value = _snapshot()
    codec = AlarmConfigurationSourceCodec()

    resource = codec.encode(snapshot=value, published_by='manager-user')
    decoded = codec.decode((resource,))

    assert ALARM_CONFIGURATION_SOURCE_SCHEMA_VERSION == 3
    assert resource.logical_path == ALARM_CONFIGURATION_SOURCE_RESOURCE_PATH
    assert decoded.snapshot == value
    assert decoded.published_by == 'manager-user'


def test_alarm_configuration_source_payload_changes_when_only_tool_revision_changes() -> None:
    codec = AlarmConfigurationSourceCodec()
    first = codec.encode(snapshot=_snapshot('tools-r1'), published_by='manager-user')
    second = codec.encode(snapshot=_snapshot('tools-r2'), published_by='manager-user')

    assert first.content != second.content


def test_alarm_configuration_source_service_preserves_generic_concurrency_contract() -> None:
    source_key = SourceKey('ada-command-center-alarms')
    current_ref = _release_ref('current')
    current = SourceSnapshot(
        source_key=source_key,
        current=SourceReleaseSummary(
            release_ref=current_ref,
            content_hash=Digest('sha256', 'abc'),
        ),
        concurrency_token=ConcurrencyToken('etag-1'),
    )

    class SourceStoreStub:
        def __init__(self) -> None:
            self.request = None

        def get_current(self, requested_source_key):
            assert requested_source_key == source_key
            return current

        def read_release(self, requested_source_key, release_ref):
            raise AssertionError((requested_source_key, release_ref))

        def publish(self, request):
            self.request = request
            published_ref = _release_ref('published')
            metadata = SourceReleaseMetadata(
                schema_version=1,
                source_key=source_key,
                release_ref=published_ref,
                content_hash=Digest('sha256', 'def'),
                resources=(),
                basis_release=current_ref,
            )
            snapshot = SourceSnapshot(
                source_key=source_key,
                current=SourceReleaseSummary(
                    release_ref=published_ref,
                    content_hash=metadata.content_hash,
                ),
                concurrency_token=ConcurrencyToken('etag-2'),
            )
            return PublishResult(release=metadata, snapshot=snapshot)

        def query_history(self, query):
            return HistoryPage(items=())

        def verify_release(self, requested_source_key, release_ref):
            raise AssertionError((requested_source_key, release_ref))

    store = SourceStoreStub()
    service = AlarmConfigurationSourceService(source=store, source_key=source_key)

    service.publish_snapshot(
        _snapshot(),
        published_by='manager-user',
        expected_concurrency_token=current.concurrency_token,
        basis_release=current_ref,
    )

    assert store.request is not None
    assert store.request.source_key == source_key
    assert store.request.expected_concurrency_token == current.concurrency_token
    assert store.request.basis_release == current_ref
    assert len(store.request.resources) == 1


def test_alarm_configuration_source_service_delegates_history() -> None:
    source_key = SourceKey('ada-command-center-alarms')

    class SourceStoreStub:
        def get_current(self, requested_source_key):
            raise AssertionError(requested_source_key)

        def read_release(self, requested_source_key, release_ref):
            raise AssertionError((requested_source_key, release_ref))

        def publish(self, request):
            raise AssertionError(request)

        def query_history(self, query):
            assert query.source_key == source_key
            assert query.page_size == 10
            return HistoryPage(items=())

        def verify_release(self, requested_source_key, release_ref):
            raise AssertionError((requested_source_key, release_ref))

    service = AlarmConfigurationSourceService(source=SourceStoreStub(), source_key=source_key)

    page = service.query_history(page_size=10)

    assert page.items == ()
