from __future__ import annotations

from ada.web.access.configuration.errors import AdaAccessConfigurationProjectionError
from ada.web.access.configuration.models import AdaAccessConfiguration
from ada.web.access.configuration.source_release import AdaAccessSourceCodec
from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.projection.service import ProjectionBuilder, SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey, SourceReleaseMetadata, SourceResource
from atlanticus.web.source.store import SourceStore


class AdaAccessProjectionBuilder(ProjectionBuilder[AdaAccessConfiguration]):
    def __init__(
        self,
        *,
        profiles_projection: ProjectionStore[ProfileCatalog],
        profiles_source_key: SourceKey,
        codec: AdaAccessSourceCodec | None = None,
    ) -> None:
        self._profiles_projection = profiles_projection
        self._profiles_source_key = profiles_source_key
        self._codec = codec or AdaAccessSourceCodec()

    def build(
        self,
        *,
        target: ProjectionTarget,
        release: SourceReleaseMetadata,
        resources: tuple[SourceResource, ...],
    ) -> AdaAccessConfiguration:
        del release
        dependency = _require_profiles_dependency(target, self._profiles_source_key)
        profiles = self._profiles_projection.get_active(self._profiles_source_key)
        if profiles is None:
            raise AdaAccessConfigurationProjectionError('Profiles projection is not available')
        if profiles.target != dependency:
            raise AdaAccessConfigurationProjectionError(
                'Profiles projection changed before ADA Access projection'
            )
        if not isinstance(profiles.payload, ProfileCatalog):
            raise AdaAccessConfigurationProjectionError('Profiles projection payload is invalid')
        configuration = self._codec.decode(resources).configuration
        try:
            configuration.validate_profiles(profiles.payload)
        except ProfilesDefinitionError as error:
            raise AdaAccessConfigurationProjectionError(
                'Published ADA Access configuration is not valid for projection'
            ) from error
        return configuration


def create_ada_access_projection_service(
    *,
    source: SourceStore,
    projection: ProjectionStore[AdaAccessConfiguration],
    profiles_projection: ProjectionStore[ProfileCatalog],
    profiles_source_key: SourceKey,
) -> SourceProjectionService[AdaAccessConfiguration]:
    def select_dependencies(_source_key: SourceKey) -> tuple[ProjectionTarget, ...]:
        dependency = profiles_projection.get_active(profiles_source_key)
        if dependency is None:
            raise AdaAccessConfigurationProjectionError('Profiles projection is not available')
        if not isinstance(dependency.payload, ProfileCatalog):
            raise AdaAccessConfigurationProjectionError('Profiles projection payload is invalid')
        return (dependency.target,)

    return SourceProjectionService(
        source=source,
        projection=projection,
        builder=AdaAccessProjectionBuilder(
            profiles_projection=profiles_projection,
            profiles_source_key=profiles_source_key,
        ),
        dependency_selector=select_dependencies,
    )


def _require_profiles_dependency(
    target: ProjectionTarget,
    profiles_source_key: SourceKey,
) -> ProjectionTarget:
    if len(target.dependencies) != 1:
        raise AdaAccessConfigurationProjectionError(
            'ADA Access projection target must contain exactly one Profiles dependency'
        )
    dependency = target.dependencies[0]
    if dependency.source_key != profiles_source_key:
        raise AdaAccessConfigurationProjectionError(
            'ADA Access projection target contains a different dependency source key'
        )
    return dependency
