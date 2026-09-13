# Este módulo conecta una release exacta de Source con Projection Core para Navigation.
from __future__ import annotations

from collections.abc import Callable

from atlanticus.web.navigation.configuration.errors import NavigationConfigurationProjectionError
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.navigation.configuration.projection import NavigationProjectionIssue
from atlanticus.web.navigation.configuration.source_release import NavigationSourceCodec
from atlanticus.web.projection.service import ProjectionBuilder, SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceReleaseMetadata, SourceResource
from atlanticus.web.source.store import SourceStore

NavigationProjectionValidator = Callable[
    [NavigationConfigurationCatalog],
    tuple[NavigationProjectionIssue, ...],
# Los validadores siguen siendo inyectables para que la composición pueda imponer reglas externas sin acoplar Users.
]


class NavigationProjectionBuilder(ProjectionBuilder[NavigationConfigurationCatalog]):
    def __init__(
        self,
        *,
# El builder sólo transforma recursos de una release ya seleccionada; nunca consulta Source current.
        codec: NavigationSourceCodec | None = None,
        validators: tuple[NavigationProjectionValidator, ...] = (),
    ) -> None:
        self._codec = codec or NavigationSourceCodec()
        self._validators = validators

    def build(
        self,
        *,
        release: SourceReleaseMetadata,
        resources: tuple[SourceResource, ...],
    ) -> NavigationConfigurationCatalog:
        catalog = self._codec.decode(resources).catalog
        catalog.to_definition()
        issues = tuple(issue for validator in self._validators for issue in validator(catalog))
        if any(issue.level == 'error' for issue in issues):
            raise NavigationConfigurationProjectionError(
                'Published navigation configuration is not valid for projection'
            )
# La validación ocurre sobre el catálogo publicado exacto antes de reemplazar la proyección activa.
        return catalog


def create_navigation_projection_service(
    *,
    source: SourceStore,
    projection: ProjectionStore[NavigationConfigurationCatalog],
    validators: tuple[NavigationProjectionValidator, ...] = (),
) -> SourceProjectionService[NavigationConfigurationCatalog]:
    return SourceProjectionService(
# La factory reutiliza SourceProjectionService; Navigation aporta únicamente codec, builder y validadores de dominio.
        source=source,
        projection=projection,
        builder=NavigationProjectionBuilder(validators=validators),
    )
