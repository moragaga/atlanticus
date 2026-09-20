from __future__ import annotations

from ada.web.kpis.registry.errors import KpiRegistryValidationError
from ada.web.kpis.registry.models import KpiRegistry
from ada.web.kpis.registry.configuration.destinations import (
    KpiDestinationCatalogProvider,
    validate_kpi_registry_destinations,
)
from ada.web.kpis.registry.configuration.errors import KpiRegistryProjectionError
from ada.web.kpis.registry.configuration.source_release import KpiRegistrySourceCodec
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.projection.service import ProjectionBuilder, SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey, SourceReleaseMetadata, SourceResource
from atlanticus.web.source.store import SourceStore


class KpiRegistryProjectionBuilder(ProjectionBuilder[KpiRegistry]):
    def __init__(
        self,
        *,
        destinations: KpiDestinationCatalogProvider,
        codec: KpiRegistrySourceCodec | None = None,
    ) -> None:
        self._destinations = destinations
        self._codec = codec or KpiRegistrySourceCodec()

    def build(
        self,
        *,
        target: ProjectionTarget,
        release: SourceReleaseMetadata,
        resources: tuple[SourceResource, ...],
    ) -> KpiRegistry:
        del release
        dependency = _require_tool_dependency(target)
        snapshot = self._destinations.load()
        if snapshot is None:
            raise KpiRegistryProjectionError('Tool projection is not available')
        if snapshot.projection_target != dependency:
            raise KpiRegistryProjectionError('Tool projection changed before KPI Registry projection')
        registry = self._codec.decode(resources).registry
        try:
            validate_kpi_registry_destinations(registry, snapshot.catalog)
        except KpiRegistryValidationError as error:
            raise KpiRegistryProjectionError(
                'Published KPI Registry is not valid for projection'
            ) from error
        return registry


def create_kpi_registry_projection_service(
    *,
    source: SourceStore,
    projection: ProjectionStore[KpiRegistry],
    destinations: KpiDestinationCatalogProvider,
) -> SourceProjectionService[KpiRegistry]:
    def select_dependencies(_source_key: SourceKey) -> tuple[ProjectionTarget, ...]:
        snapshot = destinations.load()
        if snapshot is None:
            raise KpiRegistryProjectionError('Tool projection is not available')
        return (snapshot.projection_target,)

    return SourceProjectionService(
        source=source,
        projection=projection,
        builder=KpiRegistryProjectionBuilder(destinations=destinations),
        dependency_selector=select_dependencies,
    )


def _require_tool_dependency(target: ProjectionTarget) -> ProjectionTarget:
    if len(target.dependencies) != 1:
        raise KpiRegistryProjectionError(
            'KPI Registry projection target must contain exactly one Tool dependency'
        )
    return target.dependencies[0]
