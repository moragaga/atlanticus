from __future__ import annotations

import logging

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
from atlanticus.connectivity.cosmos import CosmosClient, CosmosError
from atlanticus.connectivity.storage import StorageClient, StorageError
from atlanticus.web.application import create_web_application
from atlanticus.web.models import WebApplicationRuntime

_LOGGER = logging.getLogger(__name__)


# El composition root resuelve Tool primero y sólo después decide si existe una capability Collector.
def create_operational_application_runtime(
    *,
    settings: AdaGenericSettings | None = None,
) -> WebApplicationRuntime:
    if settings is not None and not isinstance(settings, AdaGenericSettings):
        raise TypeError('settings must be AdaGenericSettings')
    resolved_settings = settings or AdaGenericSettings()
    resolution = _resolve_tool_projection(resolved_settings)
    definition = create_definition_from_tool_resolution(resolution)

    # Sin Tool READY no existe estructura contra la cual construir stores KPI.
    if resolution.state is not ToolProjectionResolutionState.READY:
        return create_web_application(definition)
    projection = resolution.projection
    if projection is None:
        raise RuntimeError('READY Tool Projection resolution has no projection')

    # La ausencia completa de configuración KPI degrada la capability, no la aplicación.
    kpi_cosmos_settings = resolved_settings.kpi_delivery_cosmos_settings()
    if kpi_cosmos_settings is None:
        _LOGGER.info('KPI Collector is not configured')
        return create_web_application(definition)

    # Este cliente pasa a ser parte del grafo de vida del Collector; no se cierra tras composición.
    kpi_cosmos_client = CosmosClient(settings=kpi_cosmos_settings)
    try:
        definition = attach_operational_kpi_collector(
            definition,
            tool_projection=projection,
            cosmos_client=kpi_cosmos_client,
            reader_settings=resolved_settings.kpi_delivery_reader_settings(),
        )
        return create_web_application(definition)
    except Exception:
        # Si la Web no alcanza a construirse, no queda ningún runtime que posea el cliente.
        _close_client(kpi_cosmos_client, 'KPI Delivery Cosmos')
        raise


# Los clientes usados sólo para resolver Tool conservan lifecycle corto y se cierran tras la lectura.
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


# El cierre degradado de un cliente de bootstrap no debe ocultar el resultado ya resuelto.
def _close_client(client: StorageClient | CosmosClient | None, provider_name: str) -> None:
    if client is None:
        return
    try:
        client.close()
    except (StorageError, CosmosError) as error:
        _LOGGER.warning('Could not close %s client: %s', provider_name, error)
