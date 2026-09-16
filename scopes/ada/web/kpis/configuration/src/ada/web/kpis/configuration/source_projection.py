from __future__ import annotations

from ada.web.kpis.configuration.destinations import (
    KpiDestinationCatalogProvider,
    validate_kpi_configuration_destinations,
)
from ada.web.kpis.configuration.errors import (
    KpiConfigurationProjectionError,
    KpiConfigurationValidationError,
)
from ada.web.kpis.configuration.models import KpiConfiguration
from ada.web.kpis.configuration.source_release import KpiSourceCodec
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.projection.service import ProjectionBuilder, SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey, SourceReleaseMetadata, SourceResource
from atlanticus.web.source.store import SourceStore


class KpiProjectionBuilder(ProjectionBuilder[KpiConfiguration]):
    def __init__(
        self,
        *,
        destinations: KpiDestinationCatalogProvider,
        codec: KpiSourceCodec | None = None,
    ) -> None:
        self._destinations = destinations
        self._codec = codec or KpiSourceCodec()

    def build(
        self,
        *,
        target: ProjectionTarget,
        release: SourceReleaseMetadata,
        resources: tuple[SourceResource, ...],
    ) -> KpiConfiguration:
        del release
        dependency = _require_tool_dependency(target)
        snapshot = self._destinations.load()
        if snapshot is None:
            raise KpiConfigurationProjectionError('Tool projection is not available')
        if snapshot.projection_target != dependency:
            raise KpiConfigurationProjectionError('Tool projection changed before KPI projection')
        configuration = self._codec.decode(resources).configuration
        try:
            validate_kpi_configuration_destinations(configuration, snapshot.catalog)
        except KpiConfigurationValidationError as error:
            raise KpiConfigurationProjectionError(
                'Published KPI Configuration is not valid for projection'
            ) from error
        return configuration


def create_kpi_projection_service(
    *,
    source: SourceStore,
    projection: ProjectionStore[KpiConfiguration],
    destinations: KpiDestinationCatalogProvider,
) -> SourceProjectionService[KpiConfiguration]:
    def select_dependencies(_source_key: SourceKey) -> tuple[ProjectionTarget, ...]:
        snapshot = destinations.load()
        if snapshot is None:
            raise KpiConfigurationProjectionError('Tool projection is not available')
        return (snapshot.projection_target,)

    return SourceProjectionService(
        source=source,
        projection=projection,
        builder=KpiProjectionBuilder(destinations=destinations),
        dependency_selector=select_dependencies,
    )


def _require_tool_dependency(target: ProjectionTarget) -> ProjectionTarget:
    if len(target.dependencies) != 1:
        raise KpiConfigurationProjectionError(
            'KPI projection target must contain exactly one Tool dependency'
        )
    return target.dependencies[0]
