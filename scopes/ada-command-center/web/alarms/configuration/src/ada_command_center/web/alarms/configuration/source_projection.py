from __future__ import annotations

from ada_command_center.domain.alarms import AlarmConfigurationSnapshot
from ada_command_center.web.alarms.configuration.source_release import AlarmConfigurationSourceCodec
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.projection.service import ProjectionBuilder, SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceReleaseMetadata, SourceResource
from atlanticus.web.source.store import SourceStore


class AlarmConfigurationProjectionBuilder(ProjectionBuilder[AlarmConfigurationSnapshot]):
    def __init__(self, *, codec: AlarmConfigurationSourceCodec | None = None) -> None:
        self._codec = codec or AlarmConfigurationSourceCodec()

    def build(
        self,
        *,
        target: ProjectionTarget,
        release: SourceReleaseMetadata,
        resources: tuple[SourceResource, ...],
    ) -> AlarmConfigurationSnapshot:
        del target, release
        return self._codec.decode(resources).snapshot


def create_alarm_configuration_projection_service(
    *,
    source: SourceStore,
    projection: ProjectionStore[AlarmConfigurationSnapshot],
) -> SourceProjectionService[AlarmConfigurationSnapshot]:
    return SourceProjectionService(
        source=source,
        projection=projection,
        builder=AlarmConfigurationProjectionBuilder(),
    )
