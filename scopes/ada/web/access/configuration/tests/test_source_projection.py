from datetime import UTC, datetime

import pytest

from ada.web.access.configuration import (
    AdaAccessConfiguration,
    AdaAccessConfigurationProjectionError,
    AdaAccessSourceCodec,
    create_ada_access_projection_service,
)
from ada.web.access.models import ProfileAccessGrant
from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition
from atlanticus.web.projection.errors import ProjectionExecutionError
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
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


def _release_ref(value: str, *, hour: int = 12) -> SourceReleaseRef:
    return SourceReleaseRef(
        release_id=SourceReleaseId(value),
        published_at_utc=datetime(2026, 9, 19, hour, tzinfo=UTC),
    )


def _profiles_projection(
    *,
    release: str = 'profiles-1',
    profiles: tuple[ProfileDefinition, ...] = (),
) -> ProjectionRecord[ProfileCatalog]:
    source_key = SourceKey('profiles-configuration')
    release_ref = _release_ref(release, hour=10)
    return ProjectionRecord(
        source_key=source_key,
        source_release_id=release_ref.release_id,
        source_published_at_utc=release_ref.published_at_utc,
        projected_at_utc=datetime(2026, 9, 19, 10, 1, tzinfo=UTC),
        payload=ProfileCatalog(profiles=profiles),
    )


def _configuration(profile_key: str = 'basic') -> AdaAccessConfiguration:
    return AdaAccessConfiguration(
        profile_access=(
            ProfileAccessGrant(
                profile_key=profile_key,
                access_keys=('alarms.view',),
            ),
        )
    )


class ProjectionStoreStub:
    def __init__(self, value=None) -> None:
        self.value = value
        self.calls = 0

    def get_active(self, source_key):
        if self.value is None:
            return None
        assert self.value.source_key == source_key
        return self.value

    def replace_active(self, projection):
        self.calls += 1
        self.value = projection
        return projection


class SourceStoreStub:
    def __init__(self, *, source_key, release_ref, resources=()) -> None:
        self.source_key = source_key
        self.release_ref = release_ref
        self.resources = tuple(resources)

    def get_current(self, source_key):
        assert source_key == self.source_key
        return SourceSnapshot(
            source_key=source_key,
            current=SourceReleaseSummary(
                release_ref=self.release_ref,
                content_hash=Digest('sha256', 'abc'),
            ),
            concurrency_token=ConcurrencyToken('etag-1'),
        )

    def read_release(self, source_key, release_ref):
        assert source_key == self.source_key
        assert release_ref == self.release_ref
        return (
            SourceReleaseMetadata(
                schema_version=1,
                source_key=source_key,
                release_ref=release_ref,
                content_hash=Digest('sha256', 'abc'),
                resources=(),
            ),
            self.resources,
        )

    def verify_release(self, source_key, release_ref):
        assert source_key == self.source_key
        assert release_ref == self.release_ref

    def query_history(self, query):
        raise AssertionError(query)

    def publish(self, request):
        raise AssertionError(request)


def test_service_selects_current_target_with_exact_profiles_projection_dependency() -> None:
    source_key = SourceKey('ada-access')
    source_ref = _release_ref('access-1')
    profiles = _profiles_projection()
    service = create_ada_access_projection_service(
        source=SourceStoreStub(source_key=source_key, release_ref=source_ref),
        projection=ProjectionStoreStub(),
        profiles_projection=ProjectionStoreStub(profiles),
        profiles_source_key=profiles.source_key,
    )

    target = service.select_current_target(source_key)

    assert target is not None
    assert target.source_release == source_ref
    assert target.dependencies == (profiles.target,)


def test_projection_persists_configuration_with_profiles_dependency() -> None:
    source_key = SourceKey('ada-access')
    source_ref = _release_ref('access-1')
    profiles = _profiles_projection()
    resource = AdaAccessSourceCodec().encode(
        configuration=_configuration(),
        published_by='manager-user',
    )
    projection = ProjectionStoreStub()
    service = create_ada_access_projection_service(
        source=SourceStoreStub(
            source_key=source_key,
            release_ref=source_ref,
            resources=(resource,),
        ),
        projection=projection,
        profiles_projection=ProjectionStoreStub(profiles),
        profiles_source_key=profiles.source_key,
    )
    target = service.select_current_target(source_key)
    assert target is not None

    result = service.project(target)

    assert result.projection.payload == _configuration()
    assert result.projection.dependencies == (profiles.target,)
    assert result.projection.target == target
    assert projection.calls == 1


def test_projection_accepts_configured_profile_from_profiles_projection() -> None:
    configured = ProfileDefinition(
        key='11111111-1111-4111-8111-111111111111',
        label='Analista',
        background_color='#123456',
    )
    profiles = _profiles_projection(profiles=(configured,))
    source_key = SourceKey('ada-access')
    source_ref = _release_ref('access-1')
    resource = AdaAccessSourceCodec().encode(
        configuration=_configuration(configured.key),
        published_by='manager-user',
    )
    service = create_ada_access_projection_service(
        source=SourceStoreStub(
            source_key=source_key,
            release_ref=source_ref,
            resources=(resource,),
        ),
        projection=ProjectionStoreStub(),
        profiles_projection=ProjectionStoreStub(profiles),
        profiles_source_key=profiles.source_key,
    )
    target = service.select_current_target(source_key)
    assert target is not None

    result = service.project(target)

    assert result.projection.payload.resolve(
        configured.key,
        profiles=profiles.payload,
    ).access_keys == ('alarms.view',)


def test_projection_rejects_profile_missing_from_profiles_projection() -> None:
    source_key = SourceKey('ada-access')
    source_ref = _release_ref('access-1')
    profiles = _profiles_projection()
    resource = AdaAccessSourceCodec().encode(
        configuration=_configuration('missing'),
        published_by='manager-user',
    )
    service = create_ada_access_projection_service(
        source=SourceStoreStub(
            source_key=source_key,
            release_ref=source_ref,
            resources=(resource,),
        ),
        projection=ProjectionStoreStub(),
        profiles_projection=ProjectionStoreStub(profiles),
        profiles_source_key=profiles.source_key,
    )
    target = service.select_current_target(source_key)
    assert target is not None

    with pytest.raises(ProjectionExecutionError) as error:
        service.project(target)

    assert isinstance(error.value.__cause__, AdaAccessConfigurationProjectionError)
    assert str(error.value.__cause__) == (
        'Published ADA Access configuration is not valid for projection'
    )


def test_projection_fails_if_profiles_projection_changes_after_target_selection() -> None:
    source_key = SourceKey('ada-access')
    source_ref = _release_ref('access-1')
    profiles_store = ProjectionStoreStub(_profiles_projection(release='profiles-1'))
    resource = AdaAccessSourceCodec().encode(
        configuration=_configuration(),
        published_by='manager-user',
    )
    projection = ProjectionStoreStub()
    service = create_ada_access_projection_service(
        source=SourceStoreStub(
            source_key=source_key,
            release_ref=source_ref,
            resources=(resource,),
        ),
        projection=projection,
        profiles_projection=profiles_store,
        profiles_source_key=profiles_store.value.source_key,
    )
    target = service.select_current_target(source_key)
    assert target is not None
    profiles_store.value = _profiles_projection(release='profiles-2')

    with pytest.raises(ProjectionExecutionError) as error:
        service.project(target)

    assert isinstance(error.value.__cause__, AdaAccessConfigurationProjectionError)
    assert str(error.value.__cause__) == (
        'Profiles projection changed before ADA Access projection'
    )
    assert projection.calls == 0


def test_target_selection_requires_profiles_projection() -> None:
    source_key = SourceKey('ada-access')
    profiles_source_key = SourceKey('profiles-configuration')
    service = create_ada_access_projection_service(
        source=SourceStoreStub(
            source_key=source_key,
            release_ref=_release_ref('access-1'),
        ),
        projection=ProjectionStoreStub(),
        profiles_projection=ProjectionStoreStub(),
        profiles_source_key=profiles_source_key,
    )

    with pytest.raises(
        AdaAccessConfigurationProjectionError,
        match='Profiles projection is not available',
    ):
        service.select_current_target(source_key)


def test_projection_target_rejects_different_dependency_source_key() -> None:
    source_key = SourceKey('ada-access')
    source_ref = _release_ref('access-1')
    profiles = _profiles_projection()
    wrong_dependency = ProjectionTarget(
        source_key=SourceKey('other-profiles'),
        source_release=profiles.source_release,
    )
    target = ProjectionTarget(
        source_key=source_key,
        source_release=source_ref,
        dependencies=(wrong_dependency,),
    )
    release = SourceReleaseMetadata(
        schema_version=1,
        source_key=source_key,
        release_ref=source_ref,
        content_hash=Digest('sha256', 'abc'),
        resources=(),
    )

    from ada.web.access.configuration.source_projection import AdaAccessProjectionBuilder

    with pytest.raises(
        AdaAccessConfigurationProjectionError,
        match='different dependency source key',
    ):
        AdaAccessProjectionBuilder(
            profiles_projection=ProjectionStoreStub(profiles),
            profiles_source_key=profiles.source_key,
        ).build(
            target=target,
            release=release,
            resources=(
                AdaAccessSourceCodec().encode(
                    configuration=_configuration(),
                    published_by='manager-user',
                ),
            ),
        )
