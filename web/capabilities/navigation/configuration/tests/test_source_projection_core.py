from __future__ import annotations

import gzip
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from atlanticus.web.navigation.configuration import (
    NAVIGATION_SOURCE_RESOURCE_PATH,
    NavigationConfigurationCatalog,
    NavigationLinkConfiguration,
    NavigationProjectionBuilder,
    NavigationProjectionIssue,
    NavigationSourceCodec,
    NavigationSourceService,
    create_navigation_projection_service,
)
from atlanticus.web.navigation.configuration.errors import (
    NavigationConfigurationProjectionError,
    NavigationConfigurationSourceError,
)
from atlanticus.web.projection.models import ProjectionAlignment, ProjectionRecord, ProjectionTarget
from atlanticus.web.projection.store import ProjectionStore
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


def _catalog(label: str = 'Dashboard') -> NavigationConfigurationCatalog:
    return NavigationConfigurationCatalog(
        links=(
            NavigationLinkConfiguration(
                key='dashboard',
                label=label,
                href='/',
                allowed_profiles=('guest',),
            ),
        ),
    )


@dataclass(slots=True)
class _MemorySourceStore(SourceStore):
    clock_start: datetime = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    releases: list[tuple[SourceReleaseMetadata, tuple[SourceResource, ...]]] = field(
        default_factory=list
    )
    current_snapshot: SourceSnapshot | None = None
    current_reads: int = 0

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
        return IntegrityResult(
            release_ref=release_ref,
            checked_resources=len(resources),
        )


@dataclass(slots=True)
class _MemoryProjectionStore(ProjectionStore[NavigationConfigurationCatalog]):
    active: ProjectionRecord[NavigationConfigurationCatalog] | None = None

    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[NavigationConfigurationCatalog] | None:
        if self.active is None:
            return None
        assert self.active.source_key == source_key
        return self.active

    def replace_active(
        self,
        projection: ProjectionRecord[NavigationConfigurationCatalog],
    ) -> ProjectionRecord[NavigationConfigurationCatalog]:
        self.active = projection
        return projection


def test_navigation_source_codec_round_trips_compact_gzip_resource() -> None:
    codec = NavigationSourceCodec()
    catalog = _catalog()

    first = codec.encode(catalog=catalog, published_by='administrator')
    second = codec.encode(catalog=catalog, published_by='administrator')
    decoded = codec.decode((first,))
    raw = gzip.decompress(first.content)

    assert first.logical_path == NAVIGATION_SOURCE_RESOURCE_PATH
    assert b'\n' not in raw
    assert b': ' not in raw
    assert first.content == second.content
    assert decoded.catalog == catalog
    assert decoded.published_by == 'administrator'


def test_navigation_source_codec_rejects_missing_configuration_resource() -> None:
    codec = NavigationSourceCodec()

    with pytest.raises(NavigationConfigurationSourceError):
        codec.decode((SourceResource(logical_path='other.json.gz', content=b'payload'),))


def test_same_content_republish_creates_distinct_source_release() -> None:
    source_key = SourceKey('navigation-configuration')
    store = _MemorySourceStore()
    service = NavigationSourceService(source=store, source_key=source_key)
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


def test_publish_uses_caller_concurrency_token_without_prereading_source() -> None:
    source_key = SourceKey('navigation-configuration')
    store = _MemorySourceStore()
    service = NavigationSourceService(source=store, source_key=source_key)

    first = service.publish_catalog(
        _catalog(),
        published_by='administrator',
        expected_concurrency_token=None,
        basis_release=None,
    )
    reads_after_first_publish = store.current_reads

    service.publish_catalog(
        _catalog('Operations'),
        published_by='administrator',
        expected_concurrency_token=first.snapshot.concurrency_token,
        basis_release=first.release.release_ref,
    )

    assert store.current_reads == reads_after_first_publish + 1


def test_load_current_reads_the_release_selected_by_snapshot() -> None:
    source_key = SourceKey('navigation-configuration')
    store = _MemorySourceStore()
    service = NavigationSourceService(source=store, source_key=source_key)
    first = service.publish_catalog(
        _catalog('First'),
        published_by='administrator',
        expected_concurrency_token=None,
        basis_release=None,
    )
    base_snapshot = first.snapshot
    second = service.publish_catalog(
        _catalog('Second'),
        published_by='administrator',
        expected_concurrency_token=first.snapshot.concurrency_token,
        basis_release=first.release.release_ref,
    )
    store.current_snapshot = base_snapshot

    loaded = service.load_current()

    store.current_snapshot = second.snapshot
    assert loaded is not None
    assert loaded.release_ref == first.release.release_ref
    assert loaded.catalog == _catalog('First')


def test_projection_builder_rejects_domain_validator_errors() -> None:
    codec = NavigationSourceCodec()
    resource = codec.encode(catalog=_catalog(), published_by='administrator')
    source_key = SourceKey('navigation-configuration')
    release_ref = SourceReleaseRef(
        release_id=SourceReleaseId('release-1'),
        published_at_utc=datetime(2026, 9, 12, 12, 0, tzinfo=UTC),
    )
    metadata = SourceReleaseMetadata(
        schema_version=1,
        source_key=source_key,
        release_ref=release_ref,
        content_hash=Digest('sha256', 'content'),
        resources=(
            SourceResourceMetadata(
                logical_path=resource.logical_path,
                byte_length=len(resource.content),
                digest=Digest('sha256', hashlib.sha256(resource.content).hexdigest()),
            ),
        ),
    )
    builder = NavigationProjectionBuilder(
        validators=(
            lambda _catalog: (
                NavigationProjectionIssue(code='blocked', message='Blocked by composition'),
            ),
        )
    )

    with pytest.raises(NavigationConfigurationProjectionError):
        builder.build(release=metadata, resources=(resource,))


def test_exact_release_projection_remains_r1_after_source_advances_to_r2() -> None:
    source_key = SourceKey('navigation-configuration')
    source = _MemorySourceStore()
    domain = NavigationSourceService(source=source, source_key=source_key)
    projection = _MemoryProjectionStore()
    projection_service = create_navigation_projection_service(
        source=source,
        projection=projection,
    )
    first = domain.publish_catalog(
        _catalog('R1'),
        published_by='administrator',
        expected_concurrency_token=None,
        basis_release=None,
    )
    target = ProjectionTarget(
        source_key=source_key,
        source_release=first.release.release_ref,
    )
    second = domain.publish_catalog(
        _catalog('R2'),
        published_by='administrator',
        expected_concurrency_token=first.snapshot.concurrency_token,
        basis_release=first.release.release_ref,
    )
    reads_before_projection = source.current_reads

    result = projection_service.project(target)
    status = projection_service.get_status(source_key)

    assert result.target == target
    assert result.projection.source_release == first.release.release_ref
    assert result.projection.payload == _catalog('R1')
    assert projection.active == result.projection
    assert status.alignment is ProjectionAlignment.OUTDATED
    assert status.source_current_release == second.release.release_ref
    assert status.projected_source_release == first.release.release_ref
    assert source.current_reads == reads_before_projection + 1
