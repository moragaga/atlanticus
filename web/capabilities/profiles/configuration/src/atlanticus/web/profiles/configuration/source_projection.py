from __future__ import annotations

from atlanticus.web.profiles.configuration.source_release import ProfilesSourceCodec
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.projection.service import ProjectionBuilder, SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceReleaseMetadata, SourceResource
from atlanticus.web.source.store import SourceStore


class ProfilesProjectionBuilder(ProjectionBuilder[ProfileCatalog]):
    def __init__(self, *, codec: ProfilesSourceCodec | None = None) -> None:
        self._codec = codec or ProfilesSourceCodec()

    def build(
        self,
        *,
        target: ProjectionTarget,
        release: SourceReleaseMetadata,
        resources: tuple[SourceResource, ...],
    ) -> ProfileCatalog:
        del target, release
        return self._codec.decode(resources).configuration.catalog()


def create_profiles_projection_service(
    *,
    source: SourceStore,
    projection: ProjectionStore[ProfileCatalog],
) -> SourceProjectionService[ProfileCatalog]:
    return SourceProjectionService(
        source=source,
        projection=projection,
        builder=ProfilesProjectionBuilder(),
    )
