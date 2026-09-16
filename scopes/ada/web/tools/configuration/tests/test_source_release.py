from datetime import UTC, datetime

from ada.web.tools.configuration import (
    TOOL_SOURCE_RESOURCE_PATH,
    ToolSourceCodec,
    ToolSourceService,
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

from .helpers import valid_configuration


def _release_ref(value: str = 'release-1') -> SourceReleaseRef:
    return SourceReleaseRef(
        release_id=SourceReleaseId(value),
        published_at_utc=datetime(2026, 9, 16, 12, 0, tzinfo=UTC),
    )


def test_tool_source_codec_round_trips_configuration() -> None:
    configuration = valid_configuration()
    codec = ToolSourceCodec()

    resource = codec.encode(configuration=configuration, published_by='manager-user')
    decoded = codec.decode((resource,))

    assert resource.logical_path == TOOL_SOURCE_RESOURCE_PATH
    assert decoded.configuration == configuration
    assert decoded.published_by == 'manager-user'


def test_tool_source_service_publishes_with_generic_concurrency_contract() -> None:
    source_key = SourceKey('ada-tool-configuration')
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
    service = ToolSourceService(source=store, source_key=source_key)

    service.publish_configuration(
        valid_configuration(),
        published_by='manager-user',
        expected_concurrency_token=current.concurrency_token,
        basis_release=current_ref,
    )

    assert store.request is not None
    assert store.request.source_key == source_key
    assert store.request.expected_concurrency_token == current.concurrency_token
    assert store.request.basis_release == current_ref
    assert len(store.request.resources) == 1
