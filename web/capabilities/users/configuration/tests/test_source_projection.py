from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

from atlanticus.web.profiles.configuration import ProfilesConfiguration
from atlanticus.web.profiles.models import ProfileDefinition
from atlanticus.web.projection.models import ProjectionAlignment, ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceResource,
    SourceResourceMetadata,
    SourceSnapshot,
)
from atlanticus.web.users.configuration.canonical import (
    UsersConfiguration,
    UsersProfilesConfiguration,
)
from atlanticus.web.users.configuration.source_projection import (
    UsersProjectionBuilder,
    create_users_projection_service,
)
from atlanticus.web.users.configuration.source_release import UsersSourceCodec


def _payload(color: str = '#123456') -> UsersProfilesConfiguration:
    return UsersProfilesConfiguration(
        users=UsersConfiguration(),
        profiles=ProfilesConfiguration(
            profiles=(
                ProfileDefinition(
                    key='administrator',
                    label='Administrador',
                    background_color=color,
                    text_color='#FFFFFF',
                ),
            )
        ),
    )


def _release(source_key: SourceKey, release_id: str, published_at: datetime, payload: UsersProfilesConfiguration):
    resources = UsersSourceCodec().encode(
        configuration=payload.users,
        profiles=payload.profiles,
        published_by='administrator',
    )
    resource_meta = tuple(
        SourceResourceMetadata(
            logical_path=item.logical_path,
            byte_length=len(item.content),
            digest=Digest('sha256', hashlib.sha256(item.content).hexdigest()),
        )
        for item in resources
    )
    digest = Digest(
        'sha256',
        hashlib.sha256(b''.join(item.content for item in resources)).hexdigest(),
    )
    release_ref = SourceReleaseRef(SourceReleaseId(release_id), published_at)
    metadata = SourceReleaseMetadata(
        schema_version=1,
        source_key=source_key,
        release_ref=release_ref,
        content_hash=digest,
        resources=resource_meta,
    )
    return metadata, resources


@dataclass(slots=True)
class _Source:
    source_key: SourceKey
    releases: dict[SourceReleaseRef, tuple[SourceReleaseMetadata, tuple[SourceResource, ...]]]
    current_release: SourceReleaseRef
    current_reads: int = 0
    release_reads: list[SourceReleaseRef] = field(default_factory=list)
    def get_current(self, source_key: SourceKey) -> SourceSnapshot:
        assert source_key == self.source_key
        self.current_reads += 1
        metadata, _ = self.releases[self.current_release]
        return SourceSnapshot(
            source_key=source_key,
            current=SourceReleaseSummary(self.current_release, metadata.content_hash),
            concurrency_token=ConcurrencyToken('token'),
        )
    def read_release(self, source_key: SourceKey, release_ref: SourceReleaseRef):
        assert source_key == self.source_key
        self.release_reads.append(release_ref)
        return self.releases[release_ref]


@dataclass(slots=True)
class _Projection:
    active: ProjectionRecord[UsersProfilesConfiguration] | None = None
    writes: list[ProjectionRecord[UsersProfilesConfiguration]] = field(default_factory=list)
    def get_active(self, source_key: SourceKey):
        if self.active is not None:
            assert self.active.source_key == source_key
        return self.active
    def replace_active(self, projection: ProjectionRecord[UsersProfilesConfiguration]):
        self.writes.append(projection)
        self.active = projection
        return projection


def test_builder_returns_composed_contract_without_source_actor() -> None:
    source_key = SourceKey('users-configuration')
    payload = _payload()
    metadata, resources = _release(
        source_key,
        'release-1',
        datetime(2026, 9, 13, 12, tzinfo=UTC),
        payload,
    )

    projected = UsersProjectionBuilder().build(release=metadata, resources=resources)

    assert projected == payload
    assert not hasattr(projected, 'published_by')


def test_project_exact_target_does_not_reread_current() -> None:
    source_key = SourceKey('users-configuration')
    first = _release(source_key, 'release-1', datetime(2026, 9, 13, 12, tzinfo=UTC), _payload('#111111'))
    second = _release(source_key, 'release-2', datetime(2026, 9, 13, 12, 1, tzinfo=UTC), _payload('#222222'))
    first_ref = first[0].release_ref
    second_ref = second[0].release_ref
    source = _Source(source_key, {first_ref: first, second_ref: second}, second_ref)
    projection = _Projection()
    service = create_users_projection_service(source=source, projection=projection)

    result = service.project(ProjectionTarget(source_key, first_ref))

    assert source.release_reads == [first_ref]
    assert source.current_reads == 0
    assert result.projection.source_release == first_ref
    assert result.projection.payload == _payload('#111111')

    status = service.get_status(source_key)
    assert status.alignment is ProjectionAlignment.OUTDATED
    assert status.source_current_release == second_ref
    assert status.projected_source_release == first_ref


def test_same_content_distinct_release_remains_distinct_projection_target() -> None:
    source_key = SourceKey('users-configuration')
    payload = _payload()
    first = _release(source_key, 'release-1', datetime(2026, 9, 13, 12, tzinfo=UTC), payload)
    second = _release(source_key, 'release-2', datetime(2026, 9, 13, 12, 1, tzinfo=UTC), payload)
    first_ref = first[0].release_ref
    second_ref = second[0].release_ref
    source = _Source(source_key, {first_ref: first, second_ref: second}, second_ref)
    projection = _Projection()
    service = create_users_projection_service(source=source, projection=projection)

    service.project(ProjectionTarget(source_key, first_ref))
    service.project(ProjectionTarget(source_key, second_ref))

    assert [item.source_release for item in projection.writes] == [first_ref, second_ref]
