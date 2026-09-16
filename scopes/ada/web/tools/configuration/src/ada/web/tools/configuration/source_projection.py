from __future__ import annotations

from ada.web.tools.configuration.errors import ToolConfigurationProjectionError
from ada.web.tools.configuration.models import ToolConfiguration
from ada.web.tools.configuration.operational import validate_ada_operational_tool_configuration
from ada.web.tools.configuration.source_release import ToolSourceCodec
from ada.web.tools.errors import ToolConfigurationValidationError
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.projection.service import ProjectionBuilder, SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceReleaseMetadata, SourceResource
from atlanticus.web.source.store import SourceStore


class ToolProjectionBuilder(ProjectionBuilder[ToolConfiguration]):
    def __init__(self, *, codec: ToolSourceCodec | None = None) -> None:
        self._codec = codec or ToolSourceCodec()

    def build(
        self,
        *,
        target: ProjectionTarget,
        release: SourceReleaseMetadata,
        resources: tuple[SourceResource, ...],
    ) -> ToolConfiguration:
        del target, release
        configuration = self._codec.decode(resources).configuration
        try:
            validate_ada_operational_tool_configuration(configuration)
        except ToolConfigurationValidationError as error:
            raise ToolConfigurationProjectionError(
                'Published Tool Configuration is not valid for projection'
            ) from error
        return configuration


def create_tool_projection_service(
    *,
    source: SourceStore,
    projection: ProjectionStore[ToolConfiguration],
) -> SourceProjectionService[ToolConfiguration]:
    return SourceProjectionService(
        source=source,
        projection=projection,
        builder=ToolProjectionBuilder(),
    )
