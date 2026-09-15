from __future__ import annotations

from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.projection.service import ProjectionBuilder, SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceReleaseMetadata, SourceResource
from atlanticus.web.source.store import SourceStore
from atlanticus.web.users.configuration.canonical import UsersProfilesConfiguration
from atlanticus.web.users.configuration.errors import (
    UsersConfigurationProjectionError,
    UsersConfigurationSourceError,
)
from atlanticus.web.users.configuration.source_release import UsersSourceCodec


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
