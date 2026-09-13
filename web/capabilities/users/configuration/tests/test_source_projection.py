from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

from atlanticus.web.projection.models import (
    ProjectionAlignment,
    ProjectionRecord,
    ProjectionTarget,
)
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
from atlanticus.web.users.configuration import (
    UsersConfigurationCatalog,
    UsersProjectionBuilder,
    UsersSourceCodec,
    create_users_projection_service,
)


@dataclass(slots=True)
class _SourceStore:
    source_key: SourceKey
    releases: dict[
        SourceReleaseRef,
        tuple[SourceReleaseMetadata, tuple[SourceResource, ...]],
    ]
    current_release: SourceReleaseRef
    current_reads: int = 0
    release_reads: list[SourceReleaseRef] = field(default_factory=list)

    def get_current(self, source_key: SourceKey) -> SourceSnapshot:
        assert source_key == self.source_key
        self.current_reads += 1
        metadata, _resources = self.releases[self.current_release]
        return SourceSnapshot(
            source_key=source_key,
            current=SourceReleaseSummary(
                release_ref=self.current_release,
                content_hash=metadata.content_hash,
            ),
            concurrency_token=ConcurrencyToken('current-token'),
        )

    def read_release(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ) -> tuple[SourceReleaseMetadata, tuple[SourceResource, ...]]:
        assert source_key == self.source_key
        self.release_reads.append(release_ref)
        return self.releases[release_ref]


@dataclass(slots=True)
class _ProjectionStore:
    active: ProjectionRecord[UsersConfigurationCatalog] | None = None
    writes: list[ProjectionRecord[UsersConfigurationCatalog]] = field(default_factory=list)

    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[UsersConfigurationCatalog] | None:
        if self.active is None:
            return None
        assert self.active.source_key == source_key
        return self.active

    def replace_active(
        self,
        projection: ProjectionRecord[UsersConfigurationCatalog],
    ) -> ProjectionRecord[UsersConfigurationCatalog]:
        self.writes.append(projection)
        self.active = projection
        return projection


def _release(
    *,
    source_key: SourceKey,
    release_id: str,
    published_at_utc: datetime,
    catalog: UsersConfigurationCatalog,
) -> tuple[SourceReleaseMetadata, tuple[SourceResource, ...]]:
    resource = UsersSourceCodec().encode(catalog=catalog, published_by='administrator')
    digest = Digest('sha256', hashlib.sha256(resource.content).hexdigest())
    release_ref = SourceReleaseRef(
        release_id=SourceReleaseId(release_id),
        published_at_utc=published_at_utc,
    )
    metadata = SourceReleaseMetadata(
        schema_version=1,
        source_key=source_key,
        release_ref=release_ref,
        content_hash=digest,
        resources=(
            SourceResourceMetadata(
                logical_path=resource.logical_path,
                byte_length=len(resource.content),
                digest=digest,
            ),
        ),
        previous_published_release=None,
        basis_release=None,
    )
    return metadata, (resource,)


def test_users_projection_builder_returns_catalog_without_source_actor() -> None:
    source_key = SourceKey('users-configuration')
    catalog = UsersConfigurationCatalog(administrator_background_color='#123456')
    metadata, resources = _release(
        source_key=source_key,
        release_id='release-1',
        published_at_utc=datetime(2026, 9, 13, 12, 0, tzinfo=UTC),
        catalog=catalog,
    )

    projected = UsersProjectionBuilder().build(release=metadata, resources=resources)

    assert projected == catalog
    assert not hasattr(projected, 'published_by')


def test_users_projection_projects_exact_selected_release_without_rereading_current() -> None:
    source_key = SourceKey('users-configuration')
    catalog = UsersConfigurationCatalog()
    first = _release(
        source_key=source_key,
        release_id='release-1',
        published_at_utc=datetime(2026, 9, 13, 12, 0, tzinfo=UTC),
        catalog=catalog,
    )
    second = _release(
        source_key=source_key,
        release_id='release-2',
        published_at_utc=datetime(2026, 9, 13, 12, 1, tzinfo=UTC),
        catalog=catalog,
    )
    first_ref = first[0].release_ref
    second_ref = second[0].release_ref
    source = _SourceStore(
        source_key=source_key,
        releases={first_ref: first, second_ref: second},
        current_release=second_ref,
    )
    projection = _ProjectionStore()
    service = create_users_projection_service(source=source, projection=projection)

    result = service.project(ProjectionTarget(source_key=source_key, source_release=first_ref))

    assert source.release_reads == [first_ref]
    assert source.current_reads == 0
    assert result.projection.source_release == first_ref
    assert result.projection.payload == catalog

    status = service.get_status(source_key)

    assert status.alignment is ProjectionAlignment.OUTDATED
    assert status.source_current_release == second_ref
    assert status.projected_source_release == first_ref


def test_same_content_distinct_release_is_a_distinct_projection_target() -> None:
    source_key = SourceKey('users-configuration')
    catalog = UsersConfigurationCatalog()
    first = _release(
        source_key=source_key,
        release_id='release-1',
        published_at_utc=datetime(2026, 9, 13, 12, 0, tzinfo=UTC),
        catalog=catalog,
    )
    second = _release(
        source_key=source_key,
        release_id='release-2',
        published_at_utc=datetime(2026, 9, 13, 12, 1, tzinfo=UTC),
        catalog=catalog,
    )
    first_ref = first[0].release_ref
    second_ref = second[0].release_ref
    source = _SourceStore(
        source_key=source_key,
        releases={first_ref: first, second_ref: second},
        current_release=second_ref,
    )
    projection = _ProjectionStore()
    service = create_users_projection_service(source=source, projection=projection)

    service.project(ProjectionTarget(source_key=source_key, source_release=first_ref))
    result = service.project(ProjectionTarget(source_key=source_key, source_release=second_ref))

    assert [write.source_release for write in projection.writes] == [first_ref, second_ref]
    assert result.projection.payload == catalog
