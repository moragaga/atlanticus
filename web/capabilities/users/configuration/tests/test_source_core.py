from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from atlanticus.web.profiles.configuration import ProfilesConfiguration
from atlanticus.web.profiles.models import ProfileDefinition
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
from atlanticus.web.users.configuration.canonical import UsersConfiguration
from atlanticus.web.users.configuration.errors import UsersConfigurationSourceError
from atlanticus.web.users.configuration.models import UsersConfigurationCatalog
from atlanticus.web.users.configuration.source_release import (
    PROFILES_SOURCE_RESOURCE_PATH,
    USERS_SOURCE_DOCUMENT_TYPE,
    USERS_SOURCE_RESOURCE_PATH,
    UsersSourceCodec,
    UsersSourceService,
)


def _profiles(color: str = '#0F6CBD') -> ProfilesConfiguration:
    return ProfilesConfiguration(
        profiles=(
            ProfileDefinition(
                key='administrator',
                label='Administrador',
                background_color=color,
                text_color='#FFFFFF',
            ),
        )
    )


@dataclass(slots=True)
class _MemorySourceStore(SourceStore):
    clock_start: datetime = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
    releases: list[tuple[SourceReleaseMetadata, tuple[SourceResource, ...]]] = field(default_factory=list)
    current_snapshot: SourceSnapshot | None = None
    current_reads: int = 0
    published_requests: list[PublishRequest] = field(default_factory=list)

    def get_current(self, source_key: SourceKey) -> SourceSnapshot:
        self.current_reads += 1
        if self.current_snapshot is None:
            return SourceSnapshot(source_key=source_key, current=None, concurrency_token=None)
        assert self.current_snapshot.source_key == source_key
        return self.current_snapshot

    def read_release(self, source_key: SourceKey, release_ref: SourceReleaseRef):
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
        metadata_items = tuple(
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
                    resource.logical_path.encode() + b'\0' + resource.content
                    for resource in request.resources
                )
            ).hexdigest(),
        )
        metadata = SourceReleaseMetadata(
            schema_version=1,
            source_key=request.source_key,
            release_ref=release_ref,
            content_hash=content_hash,
            resources=metadata_items,
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
        return HistoryPage(
            items=tuple(
                SourceReleaseSummary(metadata.release_ref, metadata.content_hash)
                for metadata, _resources in reversed(self.releases)
                if metadata.source_key == query.source_key
            )[: query.page_size]
        )

    def verify_release(self, source_key: SourceKey, release_ref: SourceReleaseRef) -> IntegrityResult:
        _metadata, resources = self.read_release(source_key, release_ref)
        return IntegrityResult(release_ref=release_ref, checked_resources=len(resources))


def test_codec_writes_two_deterministic_resources() -> None:
    codec = UsersSourceCodec()
    first = codec.encode(
        configuration=UsersConfiguration(),
        profiles=_profiles(),
        published_by='administrator',
    )
    second = codec.encode(
        configuration=UsersConfiguration(),
        profiles=_profiles(),
        published_by='administrator',
    )

    assert [item.logical_path for item in first] == [
        USERS_SOURCE_RESOURCE_PATH,
        PROFILES_SOURCE_RESOURCE_PATH,
    ]
    assert first == second
    assert all(b'\n' not in gzip.decompress(item.content) for item in first)
    users_document = json.loads(gzip.decompress(first[0].content).decode('utf-8'))
    profiles_document = json.loads(gzip.decompress(first[1].content).decode('utf-8'))
    assert set(users_document['configuration']) == {'users'}
    assert set(profiles_document['configuration']) == {'profiles'}
    assert 'administrator_background_color' not in users_document['configuration']
    assert 'guest_background_color' not in users_document['configuration']
    decoded = codec.decode(first)
    assert decoded.configuration == UsersConfiguration()
    assert decoded.profiles == _profiles()
    assert decoded.published_by == 'administrator'


def test_v2_decode_requires_profiles_resource() -> None:
    resources = UsersSourceCodec().encode(
        configuration=UsersConfiguration(), profiles=_profiles(), published_by='administrator'
    )
    with pytest.raises(UsersConfigurationSourceError, match=PROFILES_SOURCE_RESOURCE_PATH):
        UsersSourceCodec().decode((resources[0],))


def test_legacy_v1_resource_is_normalized_without_guest_profile() -> None:
    legacy = UsersConfigurationCatalog(
        administrator_background_color='#123456',
        guest_background_color='#654321',
    )
    document = {
        'document_type': USERS_SOURCE_DOCUMENT_TYPE,
        'schema_version': 1,
        'published_by': 'legacy-admin',
        'catalog': legacy.to_document(),
    }
    resource = SourceResource(
        logical_path=USERS_SOURCE_RESOURCE_PATH,
        content=gzip.compress(
            json.dumps(document, sort_keys=True, separators=(',', ':')).encode(), mtime=0
        ),
    )

    decoded = UsersSourceCodec().decode((resource,))

    assert decoded.published_by == 'legacy-admin'
    assert [p.key for p in decoded.profiles.profiles] == ['administrator']
    assert decoded.profiles.catalog().require('administrator').background_color == '#123456'


def test_same_content_republish_keeps_distinct_release_identity() -> None:
    store = _MemorySourceStore()
    service = UsersSourceService(source=store, source_key=SourceKey('users-configuration'))
    first = service.publish_configuration(
        UsersConfiguration(),
        _profiles(),
        published_by='administrator',
        expected_concurrency_token=None,
        basis_release=None,
    )
    second = service.publish_configuration(
        UsersConfiguration(),
        _profiles(),
        published_by='administrator',
        expected_concurrency_token=first.snapshot.concurrency_token,
        basis_release=first.release.release_ref,
    )

    assert first.release.release_ref != second.release.release_ref
    assert first.release.content_hash == second.release.content_hash
    assert second.release.basis_release == first.release.release_ref
    assert len(store.published_requests[-1].resources) == 2


def test_load_current_reads_snapshot_selected_exact_release() -> None:
    store = _MemorySourceStore()
    service = UsersSourceService(source=store, source_key=SourceKey('users-configuration'))
    first = service.publish_configuration(
        UsersConfiguration(), _profiles('#111111'), published_by='a', expected_concurrency_token=None, basis_release=None
    )
    first_snapshot = first.snapshot
    second = service.publish_configuration(
        UsersConfiguration(), _profiles('#222222'), published_by='b', expected_concurrency_token=first.snapshot.concurrency_token, basis_release=first.release.release_ref
    )
    store.current_snapshot = first_snapshot

    loaded = service.load_current()

    store.current_snapshot = second.snapshot
    assert loaded is not None
    assert loaded.release_ref == first.release.release_ref
    assert loaded.profiles.catalog().require('administrator').background_color == '#111111'


def test_users_source_codec_rejects_duplicate_users_resource() -> None:
    resources = UsersSourceCodec().encode(
        configuration=UsersConfiguration(),
        profiles=_profiles(),
        published_by='administrator',
    )

    with pytest.raises(UsersConfigurationSourceError, match=USERS_SOURCE_RESOURCE_PATH):
        UsersSourceCodec().decode((resources[0], resources[0], resources[1]))


def test_publish_forwards_caller_concurrency_and_basis_without_domain_revision() -> None:
    source_key = SourceKey('users-configuration')
    store = _MemorySourceStore()
    service = UsersSourceService(source=store, source_key=source_key)
    first = service.publish_configuration(
        UsersConfiguration(),
        _profiles(),
        published_by='administrator',
        expected_concurrency_token=None,
        basis_release=None,
    )

    service.publish_configuration(
        UsersConfiguration(),
        _profiles('#123456'),
        published_by='operator',
        expected_concurrency_token=first.snapshot.concurrency_token,
        basis_release=first.release.release_ref,
    )

    request = store.published_requests[-1]
    assert request.expected_concurrency_token == first.snapshot.concurrency_token
    assert request.basis_release == first.release.release_ref
    assert request.source_key == source_key


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
    published = UsersSourceService(source=store, source_key=other_key).publish_configuration(
        UsersConfiguration(),
        _profiles(),
        published_by='administrator',
        expected_concurrency_token=None,
        basis_release=None,
    )

    with pytest.raises(UsersConfigurationSourceError, match='different source key'):
        service.load_release(published.release.release_ref)
