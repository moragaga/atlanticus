# Conecta Users Source con Projection Core sin trasladar revisiones legacy al contrato canónico.
from __future__ import annotations

from atlanticus.web.projection.service import ProjectionBuilder, SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceReleaseMetadata, SourceResource
from atlanticus.web.source.store import SourceStore
from atlanticus.web.users.configuration.errors import UsersConfigurationProjectionError
from atlanticus.web.users.configuration.models import UsersConfigurationCatalog
from atlanticus.web.users.configuration.source_release import UsersSourceCodec
from atlanticus.web.users.configuration.validation import validate_users_projection_catalog


# El builder transforma una release exacta de Source en el payload canónico de Projection.
class UsersProjectionBuilder(ProjectionBuilder[UsersConfigurationCatalog]):
    def __init__(self, *, codec: UsersSourceCodec | None = None) -> None:
        self._codec = codec or UsersSourceCodec()

    def build(
        self,
        *,
        release: SourceReleaseMetadata,
        resources: tuple[SourceResource, ...],
    ) -> UsersConfigurationCatalog:
        # El actor de publicación permanece dentro de Source; Projection sólo necesita el catálogo.
        catalog = self._codec.decode(resources).catalog
        issues = validate_users_projection_catalog(catalog)
        if any(issue.level == 'error' for issue in issues):
            raise UsersConfigurationProjectionError(
                'Published users configuration is not valid for projection'
            )
        return catalog


# La composición reutiliza el motor genérico exact-release; Users sólo aporta builder y store.
def create_users_projection_service(
    *,
    source: SourceStore,
    projection: ProjectionStore[UsersConfigurationCatalog],
) -> SourceProjectionService[UsersConfigurationCatalog]:
    return SourceProjectionService(
        source=source,
        projection=projection,
        builder=UsersProjectionBuilder(),
    )
