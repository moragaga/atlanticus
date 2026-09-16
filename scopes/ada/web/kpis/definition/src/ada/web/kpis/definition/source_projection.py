from __future__ import annotations

from ada.web.kpis.configuration import KpiConfiguration
from ada.web.kpis.definition.coverage import (
    KpiDefinitionCatalog,
    build_kpi_definition_coverage,
    validate_kpi_definition_configuration,
)
from ada.web.kpis.definition.errors import (
    KpiDefinitionProjectionError,
    KpiDefinitionValidationError,
)
from ada.web.kpis.definition.source_release import KpiDefinitionSourceCodec
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.projection.service import ProjectionBuilder, SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey, SourceReleaseMetadata, SourceResource
from atlanticus.web.source.store import SourceStore


class KpiDefinitionProjectionBuilder(ProjectionBuilder[KpiDefinitionCatalog]):
    def __init__(
        self,
        *,
        kpi_configuration_projection: ProjectionStore[KpiConfiguration],
        kpi_configuration_source_key: SourceKey,
        codec: KpiDefinitionSourceCodec | None = None,
    ) -> None:
        self._kpi_configuration_projection = kpi_configuration_projection
        self._kpi_configuration_source_key = kpi_configuration_source_key
        self._codec = codec or KpiDefinitionSourceCodec()

    def build(
        self,
        *,
        target: ProjectionTarget,
        release: SourceReleaseMetadata,
        resources: tuple[SourceResource, ...],
    ) -> KpiDefinitionCatalog:
        del release
        dependency = _require_kpi_configuration_dependency(
            target,
            self._kpi_configuration_source_key,
        )
        projection = self._kpi_configuration_projection.get_active(
            self._kpi_configuration_source_key
        )
        if projection is None:
            raise KpiDefinitionProjectionError('KPI Configuration projection is not available')
        if projection.target != dependency:
            raise KpiDefinitionProjectionError(
                'KPI Configuration projection changed before KPI Definition projection'
            )
        if not isinstance(projection.payload, KpiConfiguration):
            raise KpiDefinitionProjectionError('KPI Configuration projection payload is invalid')
        configuration = self._codec.decode(resources).configuration
        try:
            validate_kpi_definition_configuration(configuration, projection.payload)
        except KpiDefinitionValidationError as error:
            raise KpiDefinitionProjectionError(
                'Published KPI Definition is not valid for projection'
            ) from error
        return KpiDefinitionCatalog(
            configuration=configuration,
            coverage=build_kpi_definition_coverage(configuration, projection.payload),
        )


def create_kpi_definition_projection_service(
    *,
    source: SourceStore,
    projection: ProjectionStore[KpiDefinitionCatalog],
    kpi_configuration_projection: ProjectionStore[KpiConfiguration],
    kpi_configuration_source_key: SourceKey,
) -> SourceProjectionService[KpiDefinitionCatalog]:
    def select_dependencies(_source_key: SourceKey) -> tuple[ProjectionTarget, ...]:
        dependency = kpi_configuration_projection.get_active(kpi_configuration_source_key)
        if dependency is None:
            raise KpiDefinitionProjectionError('KPI Configuration projection is not available')
        if not isinstance(dependency.payload, KpiConfiguration):
            raise KpiDefinitionProjectionError('KPI Configuration projection payload is invalid')
        return (dependency.target,)

    return SourceProjectionService(
        source=source,
        projection=projection,
        builder=KpiDefinitionProjectionBuilder(
            kpi_configuration_projection=kpi_configuration_projection,
            kpi_configuration_source_key=kpi_configuration_source_key,
        ),
        dependency_selector=select_dependencies,
    )


def _require_kpi_configuration_dependency(
    target: ProjectionTarget,
    kpi_configuration_source_key: SourceKey,
) -> ProjectionTarget:
    if len(target.dependencies) != 1:
        raise KpiDefinitionProjectionError(
            'KPI Definition projection target must contain exactly one KPI Configuration dependency'
        )
    dependency = target.dependencies[0]
    if dependency.source_key != kpi_configuration_source_key:
        raise KpiDefinitionProjectionError(
            'KPI Definition projection target contains a different dependency source key'
        )
    return dependency
