from __future__ import annotations

import logging

from ada.web.application.configuration_manager.composition import (
    MANAGER_ROUTE_PREFIX,
    build_configuration_manager_surface,
)
from ada.web.application.configuration_manager.dependencies import ConfigurationManagerDependencies
from ada.web.application.configuration_manager.pages import __name__ as _manager_pages_package
from ada.web.application.generic.manager_integration import integrate_manager_surface
from ada.web.application.generic.operational_collector import attach_operational_kpi_collector
from ada.web.application.generic.operational_tool import (
    create_definition_from_tool_resolution,
    resolve_operational_tool_projection,
)
from ada.web.application.generic.settings import AdaGenericSettings
from ada.web.tools.persistence import (
    ToolProjectionResolution,
    ToolProjectionResolutionState,
    compose_tool_persistence,
)
from atlanticus.connectivity.cosmos import CosmosClient, CosmosError, CosmosOperationError
from atlanticus.connectivity.storage import (
    StorageAuthenticationError,
    StorageAuthorizationError,
    StorageClient,
    StorageConnectionError,
    StorageContainerNotFoundError,
    StorageError,
    StorageOperationError,
)
from atlanticus.web.application import create_web_application
from atlanticus.web.manager import ManagerSurface
from atlanticus.web.manager.web.ids import LOCATION_ID
from atlanticus.web.models import WebApplicationDefinition, WebApplicationRuntime
from atlanticus.web.projection.errors import ProjectionStoreError
from atlanticus.web.source.errors import SourceUnavailableError
from atlanticus.web.users.errors import UsersStoreUnavailableError

_LOGGER = logging.getLogger(__name__)
_MANAGER_UNAVAILABLE_ERRORS = (
    CosmosOperationError,
    StorageAuthenticationError,
    StorageAuthorizationError,
    StorageConnectionError,
    StorageContainerNotFoundError,
    StorageOperationError,
    ProjectionStoreError,
    SourceUnavailableError,
    UsersStoreUnavailableError,
)


def create_operational_application_runtime(
    *,
    settings: AdaGenericSettings | None = None,
    manager_dependencies: ConfigurationManagerDependencies | None = None,
) -> WebApplicationRuntime:
    if settings is not None and not isinstance(settings, AdaGenericSettings):
        raise TypeError('settings must be AdaGenericSettings')
    if manager_dependencies is not None and not isinstance(
        manager_dependencies, ConfigurationManagerDependencies
    ):
        raise TypeError('manager_dependencies must be ConfigurationManagerDependencies')

    resolved_settings = settings or AdaGenericSettings()
    resolution = _resolve_tool_projection(resolved_settings)
    definition = create_definition_from_tool_resolution(resolution)
    kpi_cosmos_client = None

    try:
        if resolution.state is ToolProjectionResolutionState.READY:
            projection = resolution.projection
            if projection is None:
                raise RuntimeError('READY Tool Projection resolution has no projection')
            kpi_cosmos_settings = resolved_settings.kpi_delivery_cosmos_settings()
            if kpi_cosmos_settings is None:
                _LOGGER.info('KPI Collector is not configured')
            else:
                kpi_cosmos_client = CosmosClient(settings=kpi_cosmos_settings)
                definition = attach_operational_kpi_collector(
                    definition,
                    tool_projection=projection,
                    cosmos_client=kpi_cosmos_client,
                    reader_settings=resolved_settings.kpi_delivery_reader_settings(),
                )

        if manager_dependencies is not None:
            definition = _integrate_manager(definition, manager_dependencies)

        return create_web_application(definition)
    except Exception:
        _close_client(kpi_cosmos_client, 'KPI Delivery Cosmos')
        raise


def _integrate_manager(
    definition: WebApplicationDefinition,
    dependencies: ConfigurationManagerDependencies,
) -> WebApplicationDefinition:
    surface = ManagerSurface(build_configuration_manager_surface(dependencies))
    return integrate_manager_surface(
        definition,
        manager=surface,
        page_packages=(_manager_pages_package,),
        route_prefix=MANAGER_ROUTE_PREFIX,
        location_id=LOCATION_ID,
        unavailable_errors=_MANAGER_UNAVAILABLE_ERRORS,
    )


def _resolve_tool_projection(settings: AdaGenericSettings) -> ToolProjectionResolution:
    storage_client = _create_storage_client(settings)
    cosmos_client = _create_tool_projection_cosmos_client(settings)
    try:
        persistence = compose_tool_persistence(
            settings=settings.tool_persistence_settings(),
            storage_client=storage_client,
            cosmos_client=cosmos_client,
        )
        return resolve_operational_tool_projection(persistence)
    finally:
        _close_client(storage_client, 'Storage')
        _close_client(cosmos_client, 'Tool Projection Cosmos')


def _create_storage_client(settings: AdaGenericSettings) -> StorageClient | None:
    storage_settings = settings.storage_settings()
    if storage_settings is None:
        return None
    return StorageClient(settings=storage_settings)


def _create_tool_projection_cosmos_client(
    settings: AdaGenericSettings,
) -> CosmosClient | None:
    cosmos_settings = settings.tool_projection_cosmos_settings()
    if cosmos_settings is None:
        return None
    return CosmosClient(settings=cosmos_settings)


def _close_client(client: StorageClient | CosmosClient | None, provider_name: str) -> None:
    if client is None:
        return
    try:
        client.close()
    except (StorageError, CosmosError) as error:
        _LOGGER.warning('Could not close %s client: %s', provider_name, error)
