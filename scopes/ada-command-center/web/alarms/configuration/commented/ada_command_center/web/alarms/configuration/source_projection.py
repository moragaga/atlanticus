# Este módulo materializa una release exacta de Alarm Configuration como Projection base.
# La Projection conserva el aggregate intrínsecamente válido sin resolver Tool Catalog ni evaluators.
# B.2 consumirá esta Projection junto con sus dependencias externas en un incremento posterior.
from __future__ import annotations

from ada_command_center.domain.alarms import AlarmConfigurationSnapshot
from ada_command_center.web.alarms.configuration.source_release import AlarmConfigurationSourceCodec
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.projection.service import ProjectionBuilder, SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceReleaseMetadata, SourceResource
from atlanticus.web.source.store import SourceStore


# La proyección ya no reduce la release a AlarmConfiguration. Conserva el snapshot completo
# para que la correlación Alarm revision -> Confirmed Tool Catalog revision llegue intacta a Cosmos.
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
        # Source ya congeló la dependencia Tools. Projection sólo transporta esa realidad;
        # nunca consulta el Tool Catalog vigente ni sustituye la revisión publicada.
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
