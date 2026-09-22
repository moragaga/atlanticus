# Este módulo materializa una release exacta de Alarm Configuration como Projection base.
# La Projection conserva el aggregate intrínsecamente válido sin resolver Tool Catalog ni evaluators.
# B.2 consumirá esta Projection junto con sus dependencias externas en un incremento posterior.
from __future__ import annotations

from ada_command_center.domain.alarms import AlarmConfiguration
from ada_command_center.web.alarms.configuration.source_release import AlarmConfigurationSourceCodec
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.projection.service import ProjectionBuilder, SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceReleaseMetadata, SourceResource
from atlanticus.web.source.store import SourceStore


class AlarmConfigurationProjectionBuilder(ProjectionBuilder[AlarmConfiguration]):
    # El builder sólo decodifica la release exacta ya validada por el contrato Source.
    def __init__(self, *, codec: AlarmConfigurationSourceCodec | None = None) -> None:
        self._codec = codec or AlarmConfigurationSourceCodec()

    # No usa dependencias externas: esta es la Projection base previa a B.2.
    def build(
        self,
        *,
        target: ProjectionTarget,
        release: SourceReleaseMetadata,
        resources: tuple[SourceResource, ...],
    ) -> AlarmConfiguration:
        del target, release
        return self._codec.decode(resources).configuration


# La factory compone el contrato generic SourceProjectionService sin introducir storage específico.
def create_alarm_configuration_projection_service(
    *,
    source: SourceStore,
    projection: ProjectionStore[AlarmConfiguration],
) -> SourceProjectionService[AlarmConfiguration]:
    return SourceProjectionService(
        source=source,
        projection=projection,
        builder=AlarmConfigurationProjectionBuilder(),
    )
