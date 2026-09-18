from __future__ import annotations

import gzip
from datetime import UTC, datetime

import pytest

from ada.web.access.configuration import (
    ADA_ACCESS_SOURCE_RESOURCE_PATH,
    AdaAccessConfiguration,
    AdaAccessConfigurationSourceError,
    AdaAccessSourceCodec,
    AdaAccessSourceService,
)
from ada.web.access.models import ProfileAccessGrant, UserProfileAssignment
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
    SourceResource,
    SourceSnapshot,
)


def _configuration() -> AdaAccessConfiguration:
    return AdaAccessConfiguration(
        user_profiles=(UserProfileAssignment(user_id='user-1', profile_keys=('operator',)),),
        profile_access=(
            ProfileAccessGrant(
                profile_key='operator',
                access_keys=('navigation.view',),
            ),
        ),
    )


def _release_ref(value: str = 'release-1') -> SourceReleaseRef:
    return SourceReleaseRef(
        release_id=SourceReleaseId(value),
        published_at_utc=datetime(2026, 9, 18, 12, 0, tzinfo=UTC),
    )


def test_source_codec_round_trips_deterministic_compact_resource() -> None:
    configuration = _configuration()
    codec = AdaAccessSourceCodec()

    first = codec.encode(configuration=configuration, published_by='manager-user')
    second = codec.encode(configuration=configuration, published_by='manager-user')
    decoded = codec.decode((first,))
    raw = gzip.decompress(first.content)

    assert first.logical_path == ADA_ACCESS_SOURCE_RESOURCE_PATH
    assert first.content == second.content
    assert b'\n' not in raw
    assert b': ' not in raw
    assert decoded.configuration == configuration
    assert decoded.published_by == 'manager-user'


def test_source_codec_rejects_missing_configuration_resource() -> None:
    with pytest.raises(AdaAccessConfigurationSourceError, match='exactly one'):
        AdaAccessSourceCodec().decode(
            (SourceResource(logical_path='other.json.gz', content=b'payload'),)
        )


def test_source_service_publishes_with_generic_concurrency_contract() -> None:
    source_key = SourceKey('ada-access')
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
    AdaAccessSourceService(source=store, source_key=source_key).publish_configuration(
        _configuration(),
        published_by='manager-user',
        expected_concurrency_token=current.concurrency_token,
        basis_release=current_ref,
    )

    assert store.request is not None
    assert store.request.source_key == source_key
    assert store.request.expected_concurrency_token == current.concurrency_token
    assert store.request.basis_release == current_ref
    assert len(store.request.resources) == 1
    assert store.request.resources[0].logical_path == ADA_ACCESS_SOURCE_RESOURCE_PATH


def test_source_service_loads_exact_release_selected_by_current_snapshot() -> None:
    source_key = SourceKey('ada-access')
    release_ref = _release_ref('current')
    configuration = _configuration()
    resource = AdaAccessSourceCodec().encode(
        configuration=configuration,
        published_by='manager-user',
    )
    metadata = SourceReleaseMetadata(
        schema_version=1,
        source_key=source_key,
        release_ref=release_ref,
        content_hash=Digest('sha256', 'abc'),
        resources=(),
    )
    snapshot = SourceSnapshot(
        source_key=source_key,
        current=SourceReleaseSummary(
            release_ref=release_ref,
            content_hash=metadata.content_hash,
        ),
        concurrency_token=ConcurrencyToken('etag-1'),
    )

    class SourceStoreStub:
        def get_current(self, requested_source_key):
            assert requested_source_key == source_key
            return snapshot

        def read_release(self, requested_source_key, requested_release_ref):
            assert requested_source_key == source_key
            assert requested_release_ref == release_ref
            return metadata, (resource,)

        def publish(self, request):
            raise AssertionError(request)

        def query_history(self, query):
            return HistoryPage(items=())

        def verify_release(self, requested_source_key, requested_release_ref):
            raise AssertionError((requested_source_key, requested_release_ref))

    loaded = AdaAccessSourceService(
        source=SourceStoreStub(),
        source_key=source_key,
    ).load_current()

    assert loaded is not None
    assert loaded.release_ref == release_ref
    assert loaded.configuration == configuration
    assert loaded.published_by == 'manager-user'
