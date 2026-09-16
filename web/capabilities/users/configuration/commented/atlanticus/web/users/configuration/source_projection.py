from __future__ import annotations

from typing import Protocol

from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.projection.service import ProjectionBuilder, SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey, SourceReleaseMetadata, SourceResource
from atlanticus.web.source.store import SourceStore
from atlanticus.web.users.configuration.canonical import UsersProfilesConfiguration
from atlanticus.web.users.configuration.errors import (
    UsersConfigurationProjectionError,
    UsersConfigurationSourceError,
)
from atlanticus.web.users.configuration.source_release import UsersSourceCodec


# La materialización runtime es un colaborador interno; Manager sigue viendo sólo ProjectionStore/SourceProjectionService.
class _UsersRuntimeProjectionMaterializer(Protocol):
    def materialize(
        self,
        projection: ProjectionRecord[UsersProfilesConfiguration],
    ) -> None: ...


# El decorator conserva una sola frontera ProjectionStore y sólo marca active después de materializar runtime.
class UsersRuntimeMaterializingProjectionStore(
    ProjectionStore[UsersProfilesConfiguration]
):
    def __init__(
        self,
        *,
        projection: ProjectionStore[UsersProfilesConfiguration],
        runtime: _UsersRuntimeProjectionMaterializer,
    ) -> None:
        self._projection = projection
        self._runtime = runtime

    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[UsersProfilesConfiguration] | None:
        return self._projection.get_active(source_key)

    def replace_active(
        self,
        projection: ProjectionRecord[UsersProfilesConfiguration],
    ) -> ProjectionRecord[UsersProfilesConfiguration]:
        self._runtime.materialize(projection)
        return self._projection.replace_active(projection)


# El builder transforma la release exacta en el payload canónico Users + Profiles.
class UsersProjectionBuilder(ProjectionBuilder[UsersProfilesConfiguration]):
    def __init__(self, *, codec: UsersSourceCodec | None = None) -> None:
        self._codec = codec or UsersSourceCodec()

    def build(
        self,
        *,
        target: ProjectionTarget,
        release: SourceReleaseMetadata,
        resources: tuple[SourceResource, ...],
    ) -> UsersProfilesConfiguration:
        del target, release
        try:
            return self._codec.decode(resources).projection_payload()
        except UsersConfigurationSourceError as error:
            raise UsersConfigurationProjectionError(
                'Published users/profiles configuration is not valid for projection'
            ) from error


def create_users_projection_service(
    *,
    source: SourceStore,
    projection: ProjectionStore[UsersProfilesConfiguration],
) -> SourceProjectionService[UsersProfilesConfiguration]:
    return SourceProjectionService(
        source=source,
        projection=projection,
        builder=UsersProjectionBuilder(),
    )
