from __future__ import annotations

import gzip
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

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
    SourceResource,
    SourceResourceMetadata,
    SourceSnapshot,
)
from atlanticus.web.source.store import SourceStore
from atlanticus.web.users.configuration import (
    USERS_SOURCE_RESOURCE_PATH,
    UsersConfigurationCatalog,
    UsersSourceCodec,
    UsersSourceService,
)
from atlanticus.web.users.configuration.errors import UsersConfigurationSourceError


def _catalog(*, administrator_background_color: str = '#0F6CBD') -> UsersConfigurationCatalog:
    return UsersConfigurationCatalog(
        administrator_background_color=administrator_background_color,
    )


@dataclass(slots=True)
class _MemorySourceStore(SourceStore):
    clock_start: datetime = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
    releases: list[tuple[SourceReleaseMetadata, tuple[SourceResource, ...]]] = field(
        default_factory=list
    )
    current_snapshot: SourceSnapshot | None = None
    current_reads: int = 0
    published_requests: list[PublishRequest] = field(default_factory=list)

    def get_current(self, source_key: SourceKey) -> SourceSnapshot:
        self.current_reads += 1
        if self.current_snapshot is None:
            return SourceSnapshot(
                source_key=source_key,
                current=None,
                concurrency_token=None,
            )
        assert self.current_snapshot.source_key == source_key
        return self.current_snapshot

    def read_release(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ) -> tuple[SourceReleaseMetadata, tuple[SourceResource, ...]]:
        for metadata, resources in self.releases:
            if metadata.source_key == source_key and metadata.release_ref == release_ref:
                return metadata, resources
        raise KeyError(release_ref)

    def publish(self, request: PublishRequest) -> PublishResult:
        self.published_requests.append(request)
        current = self.get_current(request.source_key)
        if current.concurrency_token != request.expected_concurrency_token:
            raise RuntimeError('stale concurrency token')
        sequence = len(self.releases) + 1
        release_ref = SourceReleaseRef(
            release_id=SourceReleaseId(f'release-{sequence}'),
            published_at_utc=self.clock_start + timedelta(seconds=sequence),
        )
        resource_metadata = tuple(
            SourceResourceMetadata(
                logical_path=resource.logical_path,
                byte_length=len(resource.content),
                digest=Digest('sha256', hashlib.sha256(resource.content).hexdigest()),
            )
            for resource in request.resources
        )
        content_hash = Digest(
            'sha256',
            hashlib.sha256(
                b''.join(
                    resource.logical_path.encode('utf-8') + b'\0' + resource.content
                    for resource in request.resources
                )
            ).hexdigest(),
        )
        metadata = SourceReleaseMetadata(
            schema_version=1,
            source_key=request.source_key,
            release_ref=release_ref,
            content_hash=content_hash,
            resources=resource_metadata,
            previous_published_release=(
                current.current.release_ref if current.current is not None else None
            ),
            basis_release=request.basis_release,
        )
        snapshot = SourceSnapshot(
            source_key=request.source_key,
            current=SourceReleaseSummary(release_ref=release_ref, content_hash=content_hash),
            concurrency_token=ConcurrencyToken(f'token-{sequence}'),
        )
        self.releases.append((metadata, request.resources))
        self.current_snapshot = snapshot
        return PublishResult(release=metadata, snapshot=snapshot)

    def query_history(self, query: HistoryQuery) -> HistoryPage:
        summaries = tuple(
            SourceReleaseSummary(
                release_ref=metadata.release_ref,
                content_hash=metadata.content_hash,
            )
            for metadata, _resources in reversed(self.releases)
            if metadata.source_key == query.source_key
        )
        return HistoryPage(items=summaries[: query.page_size])

    def verify_release(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ) -> IntegrityResult:
        _metadata, resources = self.read_release(source_key, release_ref)
        return IntegrityResult(release_ref=release_ref, checked_resources=len(resources))


def test_users_source_codec_round_trips_compact_deterministic_gzip_resource() -> None:
    codec = UsersSourceCodec()
    catalog = _catalog()

    first = codec.encode(catalog=catalog, published_by='administrator')
    second = codec.encode(catalog=catalog, published_by='administrator')
    decoded = codec.decode((first,))
    raw = gzip.decompress(first.content)

    assert first.logical_path == USERS_SOURCE_RESOURCE_PATH
    assert b'\n' not in raw
    assert b': ' not in raw
    assert first.content == second.content
    assert decoded.catalog == catalog
    assert decoded.published_by == 'administrator'


def test_users_source_codec_rejects_missing_configuration_resource() -> None:
    codec = UsersSourceCodec()

    with pytest.raises(UsersConfigurationSourceError):
        codec.decode((SourceResource(logical_path='other.json.gz', content=b'payload'),))


def test_users_source_codec_rejects_duplicate_configuration_resource() -> None:
    codec = UsersSourceCodec()
    resource = codec.encode(catalog=_catalog(), published_by='administrator')

    with pytest.raises(UsersConfigurationSourceError):
        codec.decode((resource, resource))


def test_same_content_republish_creates_distinct_source_release() -> None:
    source_key = SourceKey('users-configuration')
    store = _MemorySourceStore()
    service = UsersSourceService(source=store, source_key=source_key)
    catalog = _catalog()

    first = service.publish_catalog(
        catalog,
        published_by='administrator',
        expected_concurrency_token=None,
        basis_release=None,
    )
    second = service.publish_catalog(
        catalog,
        published_by='administrator',
        expected_concurrency_token=first.snapshot.concurrency_token,
        basis_release=first.release.release_ref,
    )
    history = service.query_history()

    assert first.release.release_ref != second.release.release_ref
    assert first.release.content_hash == second.release.content_hash
    assert second.release.basis_release == first.release.release_ref
    assert second.release.previous_published_release == first.release.release_ref
    assert [item.release_ref for item in history.items] == [
        second.release.release_ref,
        first.release.release_ref,
    ]


def test_publish_forwards_caller_concurrency_and_basis_without_domain_revision() -> None:
    source_key = SourceKey('users-configuration')
    store = _MemorySourceStore()
    service = UsersSourceService(source=store, source_key=source_key)
    first = service.publish_catalog(
        _catalog(),
        published_by='administrator',
        expected_concurrency_token=None,
        basis_release=None,
    )

    service.publish_catalog(
        _catalog(administrator_background_color='#123456'),
        published_by='operator',
        expected_concurrency_token=first.snapshot.concurrency_token,
        basis_release=first.release.release_ref,
    )

    request = store.published_requests[-1]
    assert request.expected_concurrency_token == first.snapshot.concurrency_token
    assert request.basis_release == first.release.release_ref
    assert request.source_key == source_key


def test_load_current_reads_release_selected_by_snapshot() -> None:
    source_key = SourceKey('users-configuration')
    store = _MemorySourceStore()
    service = UsersSourceService(source=store, source_key=source_key)
    first = service.publish_catalog(
        _catalog(administrator_background_color='#111111'),
        published_by='administrator',
        expected_concurrency_token=None,
        basis_release=None,
    )
    first_snapshot = first.snapshot
    second = service.publish_catalog(
        _catalog(administrator_background_color='#222222'),
        published_by='administrator',
        expected_concurrency_token=first.snapshot.concurrency_token,
        basis_release=first.release.release_ref,
    )
    store.current_snapshot = first_snapshot

    loaded = service.load_current()

    store.current_snapshot = second.snapshot
    assert loaded is not None
    assert loaded.release_ref == first.release.release_ref
    assert loaded.catalog == _catalog(administrator_background_color='#111111')


def test_load_release_rejects_store_metadata_for_different_source_key() -> None:
    class WrongMetadataSourceStore(_MemorySourceStore):
        def read_release(
            self,
            source_key: SourceKey,
            release_ref: SourceReleaseRef,
        ) -> tuple[SourceReleaseMetadata, tuple[SourceResource, ...]]:
            del source_key
            return super().read_release(SourceKey('other-users-configuration'), release_ref)

    expected_key = SourceKey('users-configuration')
    other_key = SourceKey('other-users-configuration')
    store = WrongMetadataSourceStore()
    service = UsersSourceService(source=store, source_key=expected_key)
    published = UsersSourceService(source=store, source_key=other_key).publish_catalog(
        _catalog(),
        published_by='administrator',
        expected_concurrency_token=None,
        basis_release=None,
    )

    with pytest.raises(UsersConfigurationSourceError, match='different source key'):
        service.load_release(published.release.release_ref)
